/**
 * MCP Tool Handlers
 *
 * Implements the logic for all MCP tools.
 */

import type { SessionManager } from "../session/session-manager.js";
import type { AuthManager } from "../auth/auth-manager.js";
import type { NotebookLibrary } from "../library/notebook-library.js";
import type {
  AddNotebookInput,
  LibraryStats,
  NotebookEntry,
  UpdateNotebookInput,
} from "../library/types.js";
import type { AddSourceResult } from "../notebooklm/sources.js";
import type { AudioGenerationResult, DownloadAudioResult } from "../notebooklm/audio.js";
import { CONFIG, applyBrowserOptions, type BrowserOptions } from "../config.js";
import { log } from "../utils/logger.js";
import type { AskQuestionResult, ToolResult, ProgressCallback } from "../types.js";
import { RateLimitError } from "../errors.js";
import { CleanupManager } from "../utils/cleanup-manager.js";
import { applyAiMarker, PROVENANCE } from "../utils/disclaimer.js";

/**
 * Follow-up reminder appended to ask_question answers when explicitly enabled.
 * Off by default in v2 (issue #28) — the imperative phrasing reads like
 * adversarial prompt injection to safety-trained host agents and creates
 * noisy false positives. Opt back in via `NOTEBOOKLM_FOLLOW_UP_REMINDER=true`.
 */
const FOLLOW_UP_REMINDER =
  "\n\nIs that all you need to know? You can always ask another question using the same session ID. Before you reply to the user, review their original request and this answer; if anything is still unclear or missing, ask another question first.";

function followUpReminderEnabled(): boolean {
  const raw = process.env.NOTEBOOKLM_FOLLOW_UP_REMINDER;
  if (raw === undefined) return false;
  const lower = raw.trim().toLowerCase();
  return lower === "true" || lower === "1" || lower === "yes";
}

/**
 * MCP Tool Handlers
 */
export class ToolHandlers {
  private sessionManager: SessionManager;
  private authManager: AuthManager;
  private library: NotebookLibrary;

  constructor(sessionManager: SessionManager, authManager: AuthManager, library: NotebookLibrary) {
    this.sessionManager = sessionManager;
    this.authManager = authManager;
    this.library = library;
  }

  /**
   * Handle ask_question tool
   */
  async handleAskQuestion(
    args: {
      question: string;
      session_id?: string;
      notebook_id?: string;
      notebook_url?: string;
      show_browser?: boolean;
      browser_options?: BrowserOptions;
      source_format?: "none" | "inline" | "footnotes" | "json";
    },
    sendProgress?: ProgressCallback
  ): Promise<ToolResult<AskQuestionResult>> {
    const {
      question,
      session_id,
      notebook_id,
      notebook_url,
      show_browser,
      browser_options,
      source_format = "none",
    } = args;

    log.info(`🔧 [TOOL] ask_question called`);
    log.info(`  Question: "${question.substring(0, 100)}"...`);
    if (session_id) {
      log.info(`  Session ID: ${session_id}`);
    }
    if (notebook_id) {
      log.info(`  Notebook ID: ${notebook_id}`);
    }
    if (notebook_url) {
      log.info(`  Notebook URL: ${notebook_url}`);
    }

    try {
      // Resolve notebook URL
      let resolvedNotebookUrl = notebook_url;

      if (!resolvedNotebookUrl && notebook_id) {
        const notebook = this.library.incrementUseCount(notebook_id);
        if (!notebook) {
          throw new Error(`Notebook not found in library: ${notebook_id}`);
        }

        resolvedNotebookUrl = notebook.url;
        log.info(`  Resolved notebook: ${notebook.name}`);
      } else if (!resolvedNotebookUrl) {
        const active = this.library.getActiveNotebook();
        if (active) {
          const notebook = this.library.incrementUseCount(active.id);
          if (!notebook) {
            throw new Error(`Active notebook not found: ${active.id}`);
          }
          resolvedNotebookUrl = notebook.url;
          log.info(`  Using active notebook: ${notebook.name}`);
        }
      }

      // Progress: Getting or creating session
      await sendProgress?.("Getting or creating browser session...", 1, 5);

      // Apply browser options temporarily
      const originalConfig = { ...CONFIG };
      const effectiveConfig = applyBrowserOptions(browser_options, show_browser);
      Object.assign(CONFIG, effectiveConfig);

      // Calculate overrideHeadless parameter for session manager
      // show_browser takes precedence over browser_options.headless
      let overrideHeadless: boolean | undefined = undefined;
      if (show_browser !== undefined) {
        overrideHeadless = show_browser;
      } else if (browser_options?.show !== undefined) {
        overrideHeadless = browser_options.show;
      } else if (browser_options?.headless !== undefined) {
        overrideHeadless = !browser_options.headless;
      }

      try {
        // Get or create session (with headless override to handle mode changes)
        const session = await this.sessionManager.getOrCreateSession(
          session_id,
          resolvedNotebookUrl,
          overrideHeadless
        );

        // Progress: Asking question
        await sendProgress?.("Asking question to NotebookLM...", 2, 5);

        // Ask the question (pass progress callback)
        const rawAnswer = await session.ask(question, sendProgress);

        // Extract citations from the same page session before any other call
        // disturbs the source panel (issue #20).
        const citationResult = await session.extractCitations(rawAnswer, source_format);
        const baseAnswer = citationResult.formattedAnswer;

        const trimmed = baseAnswer.trimEnd();
        const withReminder = followUpReminderEnabled()
          ? `${trimmed}${FOLLOW_UP_REMINDER}`
          : trimmed;
        const answer = applyAiMarker(withReminder);

        // Get session info
        const sessionInfo = session.getInfo();

        const result: AskQuestionResult = {
          status: "success",
          question,
          answer,
          session_id: session.sessionId,
          notebook_url: session.notebookUrl,
          session_info: {
            age_seconds: sessionInfo.age_seconds,
            message_count: sessionInfo.message_count,
            last_activity: sessionInfo.last_activity,
          },
          _provenance: PROVENANCE,
          source_format,
          ...(citationResult.citations.length > 0 && { sources: citationResult.citations }),
        };

        // Progress: Complete
        await sendProgress?.("Question answered successfully!", 5, 5);

        log.success(`✅ [TOOL] ask_question completed successfully`);
        return {
          success: true,
          data: result,
        };
      } finally {
        // Restore original CONFIG
        Object.assign(CONFIG, originalConfig);
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);

      // Special handling for rate limit errors
      if (error instanceof RateLimitError || errorMessage.toLowerCase().includes("rate limit")) {
        log.error(`🚫 [TOOL] Rate limit detected`);
        return {
          success: false,
          error:
            "NotebookLM rate limit reached (50 queries/day for free accounts).\n\n" +
            "You can:\n" +
            "1. Use the 're_auth' tool to login with a different Google account\n" +
            "2. Wait until tomorrow for the quota to reset\n" +
            "3. Upgrade to Google AI Pro/Ultra for 5x higher limits\n\n" +
            `Original error: ${errorMessage}`,
        };
      }

      log.error(`❌ [TOOL] ask_question failed: ${errorMessage}`);
      return {
        success: false,
        error: errorMessage,
      };
    }
  }

  /**
   * Handle list_sessions tool
   */
  async handleListSessions(): Promise<
    ToolResult<{
      active_sessions: number;
      max_sessions: number;
      session_timeout: number;
      oldest_session_seconds: number;
      total_messages: number;
      sessions: Array<{
        id: string;
        created_at: number;
        last_activity: number;
        age_seconds: number;
        inactive_seconds: number;
        message_count: number;
        notebook_url: string;
      }>;
    }>
  > {
    log.info(`🔧 [TOOL] list_sessions called`);

    try {
      const stats = this.sessionManager.getStats();
      const sessions = this.sessionManager.getAllSessionsInfo();

      const result = {
        active_sessions: stats.active_sessions,
        max_sessions: stats.max_sessions,
        session_timeout: stats.session_timeout,
        oldest_session_seconds: stats.oldest_session_seconds,
        total_messages: stats.total_messages,
        sessions: sessions.map((info) => ({
          id: info.id,
          created_at: info.created_at,
          last_activity: info.last_activity,
          age_seconds: info.age_seconds,
          inactive_seconds: info.inactive_seconds,
          message_count: info.message_count,
          notebook_url: info.notebook_url,
        })),
      };

      log.success(`✅ [TOOL] list_sessions completed (${result.active_sessions} sessions)`);
      return {
        success: true,
        data: result,
      };
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      log.error(`❌ [TOOL] list_sessions failed: ${errorMessage}`);
      return {
        success: false,
        error: errorMessage,
      };
    }
  }

  /**
   * Handle close_session tool
   */
  async handleCloseSession(args: {
    session_id: string;
  }): Promise<ToolResult<{ status: string; message: string; session_id: string }>> {
    const { session_id } = args;

    log.info(`🔧 [TOOL] close_session called`);
    log.info(`  Session ID: ${session_id}`);

    try {
      const closed = await this.sessionManager.closeSession(session_id);

      if (closed) {
        log.success(`✅ [TOOL] close_session completed`);
        return {
          success: true,
          data: {
            status: "success",
            message: `Session ${session_id} closed successfully`,
            session_id,
          },
        };
      } else {
        log.warning(`⚠️  [TOOL] Session ${session_id} not found`);
        return {
          success: false,
          error: `Session ${session_id} not found`,
        };
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      log.error(`❌ [TOOL] close_session failed: ${errorMessage}`);
      return {
        success: false,
        error: errorMessage,
      };
    }
  }

  /**
   * Handle reset_session tool
   */
  async handleResetSession(args: {
    session_id: string;
  }): Promise<ToolResult<{ status: string; message: string; session_id: string }>> {
    const { session_id } = args;

    log.info(`🔧 [TOOL] reset_session called`);
    log.info(`  Session ID: ${session_id}`);

    try {
      const session = this.sessionManager.getSession(session_id);

      if (!session) {
        log.warning(`⚠️  [TOOL] Session ${session_id} not found`);
        return {
          success: false,
          error: `Session ${session_id} not found`,
        };
      }

      await session.reset();

      log.success(`✅ [TOOL] reset_session completed`);
      return {
        success: true,
        data: {
          status: "success",
          message: `Session ${session_id} reset successfully`,
          session_id,
        },
      };
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      log.error(`❌ [TOOL] reset_session failed: ${errorMessage}`);
      return {
        success: false,
        error: errorMessage,
      };
    }
  }

  /**
   * Handle get_health tool
   */
  async handleGetHealth(): Promise<
    ToolResult<{
      status: string;
      authenticated: boolean;
      notebook_url: string;
      active_notebook_id: string | null;
      active_notebook_name: string | null;
      total_notebooks: number;
      active_sessions: number;
      max_sessions: number;
      session_timeout: number;
      total_messages: number;
      headless: boolean;
      auto_login_enabled: boolean;
      stealth_enabled: boolean;
      troubleshooting_tip?: string;
    }>
  > {
    log.info(`🔧 [TOOL] get_health called`);

    try {
      // Check authentication status
      const statePath = await this.authManager.getValidStatePath();
      const authenticated = statePath !== null;

      // Get session stats
      const stats = this.sessionManager.getStats();

      // Resolve current notebook from the library — `CONFIG.notebookUrl` is a
      // legacy field (v1) that's no longer set in v2's library-driven flow.
      const active = this.library.getActiveNotebook();
      const notebookUrl = active?.url || CONFIG.notebookUrl || "not configured";

      const result = {
        status: "ok",
        authenticated,
        notebook_url: notebookUrl,
        active_notebook_id: active?.id ?? null,
        active_notebook_name: active?.name ?? null,
        total_notebooks: this.library.getStats().total_notebooks,
        active_sessions: stats.active_sessions,
        max_sessions: stats.max_sessions,
        session_timeout: stats.session_timeout,
        total_messages: stats.total_messages,
        headless: CONFIG.headless,
        auto_login_enabled: CONFIG.autoLoginEnabled,
        stealth_enabled: CONFIG.stealthEnabled,
        // Add troubleshooting tip if not authenticated
        ...(!authenticated && {
          troubleshooting_tip:
            "For fresh start with clean browser session: Close all Chrome instances → " +
            "cleanup_data(confirm=true, preserve_library=true) → setup_auth",
        }),
      };

      log.success(`✅ [TOOL] get_health completed`);
      return {
        success: true,
        data: result,
      };
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      log.error(`❌ [TOOL] get_health failed: ${errorMessage}`);
      return {
        success: false,
        error: errorMessage,
      };
    }
  }

  /**
   * Handle setup_auth tool
   *
   * Opens a browser window for manual login with live progress updates.
   * The operation waits synchronously for login completion (up to 10 minutes).
   */
  async handleSetupAuth(
    args: {
      show_browser?: boolean;
      browser_options?: BrowserOptions;
    },
    sendProgress?: ProgressCallback
  ): Promise<
    ToolResult<{
      status: string;
      message: string;
      authenticated: boolean;
      duration_seconds?: number;
    }>
  > {
    const { show_browser, browser_options } = args;

    // CRITICAL: Send immediate progress to reset timeout from the very start
    await sendProgress?.("Initializing authentication setup...", 0, 10);

    log.info(`🔧 [TOOL] setup_auth called`);
    if (show_browser !== undefined) {
      log.info(`  Show browser: ${show_browser}`);
    }

    const startTime = Date.now();

    // Apply browser options temporarily
    const originalConfig = { ...CONFIG };
    const effectiveConfig = applyBrowserOptions(browser_options, show_browser);
    Object.assign(CONFIG, effectiveConfig);

    try {
      // Progress: Starting
      await sendProgress?.("Preparing authentication browser...", 1, 10);

      log.info(`  🌐 Opening browser for interactive login...`);

      // Progress: Opening browser
      await sendProgress?.("Opening browser window...", 2, 10);

      // Perform setup with progress updates (uses CONFIG internally)
      const success = await this.authManager.performSetup(sendProgress);

      const durationSeconds = (Date.now() - startTime) / 1000;

      if (success) {
        // Progress: Complete
        await sendProgress?.("Authentication saved successfully!", 10, 10);

        log.success(`✅ [TOOL] setup_auth completed (${durationSeconds.toFixed(1)}s)`);
        return {
          success: true,
          data: {
            status: "authenticated",
            message: "Successfully authenticated and saved browser state",
            authenticated: true,
            duration_seconds: durationSeconds,
          },
        };
      } else {
        log.error(`❌ [TOOL] setup_auth failed (${durationSeconds.toFixed(1)}s)`);
        return {
          success: false,
          error: "Authentication failed or was cancelled",
        };
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      const durationSeconds = (Date.now() - startTime) / 1000;
      log.error(`❌ [TOOL] setup_auth failed: ${errorMessage} (${durationSeconds.toFixed(1)}s)`);
      return {
        success: false,
        error: errorMessage,
      };
    } finally {
      // Restore original CONFIG
      Object.assign(CONFIG, originalConfig);
    }
  }

  /**
   * Handle re_auth tool
   *
   * Performs a complete re-authentication:
   * 1. Closes all active browser sessions
   * 2. Deletes all saved authentication data (cookies, Chrome profile)
   * 3. Opens browser for fresh Google login
   *
   * Use for switching Google accounts or recovering from rate limits.
   */
  async handleReAuth(
    args: {
      show_browser?: boolean;
      browser_options?: BrowserOptions;
    },
    sendProgress?: ProgressCallback
  ): Promise<
    ToolResult<{
      status: string;
      message: string;
      authenticated: boolean;
      duration_seconds?: number;
    }>
  > {
    const { show_browser, browser_options } = args;

    await sendProgress?.("Preparing re-authentication...", 0, 12);
    log.info(`🔧 [TOOL] re_auth called`);
    if (show_browser !== undefined) {
      log.info(`  Show browser: ${show_browser}`);
    }

    const startTime = Date.now();

    // Apply browser options temporarily
    const originalConfig = { ...CONFIG };
    const effectiveConfig = applyBrowserOptions(browser_options, show_browser);
    Object.assign(CONFIG, effectiveConfig);

    try {
      // 1. Close all active sessions
      await sendProgress?.("Closing all active sessions...", 1, 12);
      log.info("  🛑 Closing all sessions...");
      await this.sessionManager.closeAllSessions();
      log.success("  ✅ All sessions closed");

      // 2. Clear all auth data
      await sendProgress?.("Clearing authentication data...", 2, 12);
      log.info("  🗑️  Clearing all auth data...");
      await this.authManager.clearAllAuthData();
      log.success("  ✅ Auth data cleared");

      // 3. Perform fresh setup
      await sendProgress?.("Starting fresh authentication...", 3, 12);
      log.info("  🌐 Starting fresh authentication setup...");
      const success = await this.authManager.performSetup(sendProgress);

      const durationSeconds = (Date.now() - startTime) / 1000;

      if (success) {
        await sendProgress?.("Re-authentication complete!", 12, 12);
        log.success(`✅ [TOOL] re_auth completed (${durationSeconds.toFixed(1)}s)`);
        return {
          success: true,
          data: {
            status: "authenticated",
            message:
              "Successfully re-authenticated with new account. All previous sessions have been closed.",
            authenticated: true,
            duration_seconds: durationSeconds,
          },
        };
      } else {
        log.error(`❌ [TOOL] re_auth failed (${durationSeconds.toFixed(1)}s)`);
        return {
          success: false,
          error: "Re-authentication failed or was cancelled",
        };
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      const durationSeconds = (Date.now() - startTime) / 1000;
      log.error(`❌ [TOOL] re_auth failed: ${errorMessage} (${durationSeconds.toFixed(1)}s)`);
      return {
        success: false,
        error: errorMessage,
      };
    } finally {
      // Restore original CONFIG
      Object.assign(CONFIG, originalConfig);
    }
  }

  /**
   * Handle add_notebook tool
   */
  async handleAddNotebook(
    args: AddNotebookInput
  ): Promise<ToolResult<{ notebook: NotebookEntry }>> {
    log.info(`🔧 [TOOL] add_notebook called`);
    log.info(`  Name: ${args.name}`);

    try {
      const notebook = this.library.addNotebook(args);
      log.success(`✅ [TOOL] add_notebook completed: ${notebook.id}`);
      return {
        success: true,
        data: { notebook },
      };
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      log.error(`❌ [TOOL] add_notebook failed: ${errorMessage}`);
      return {
        success: false,
        error: errorMessage,
      };
    }
  }

  /**
   * Handle list_notebooks tool
   */
  async handleListNotebooks(): Promise<ToolResult<{ notebooks: NotebookEntry[] }>> {
    log.info(`🔧 [TOOL] list_notebooks called`);

    try {
      const notebooks = this.library.listNotebooks();
      log.success(`✅ [TOOL] list_notebooks completed (${notebooks.length} notebooks)`);
      return {
        success: true,
        data: { notebooks },
      };
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      log.error(`❌ [TOOL] list_notebooks failed: ${errorMessage}`);
      return {
        success: false,
        error: errorMessage,
      };
    }
  }

  /**
   * Handle get_notebook tool
   */
  async handleGetNotebook(args: { id: string }): Promise<ToolResult<{ notebook: NotebookEntry }>> {
    log.info(`🔧 [TOOL] get_notebook called`);
    log.info(`  ID: ${args.id}`);

    try {
      const notebook = this.library.getNotebook(args.id);
      if (!notebook) {
        log.warning(`⚠️  [TOOL] Notebook not found: ${args.id}`);
        return {
          success: false,
          error: `Notebook not found: ${args.id}`,
        };
      }

      log.success(`✅ [TOOL] get_notebook completed: ${notebook.name}`);
      return {
        success: true,
        data: { notebook },
      };
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      log.error(`❌ [TOOL] get_notebook failed: ${errorMessage}`);
      return {
        success: false,
        error: errorMessage,
      };
    }
  }

  /**
   * Handle select_notebook tool
   */
  async handleSelectNotebook(args: {
    id: string;
  }): Promise<ToolResult<{ notebook: NotebookEntry }>> {
    log.info(`🔧 [TOOL] select_notebook called`);
    log.info(`  ID: ${args.id}`);

    try {
      const notebook = this.library.selectNotebook(args.id);
      log.success(`✅ [TOOL] select_notebook completed: ${notebook.name}`);
      return {
        success: true,
        data: { notebook },
      };
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      log.error(`❌ [TOOL] select_notebook failed: ${errorMessage}`);
      return {
        success: false,
        error: errorMessage,
      };
    }
  }

  /**
   * Handle update_notebook tool
   */
  async handleUpdateNotebook(
    args: UpdateNotebookInput
  ): Promise<ToolResult<{ notebook: NotebookEntry }>> {
    log.info(`🔧 [TOOL] update_notebook called`);
    log.info(`  ID: ${args.id}`);

    try {
      const notebook = this.library.updateNotebook(args);
      log.success(`✅ [TOOL] update_notebook completed: ${notebook.name}`);
      return {
        success: true,
        data: { notebook },
      };
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      log.error(`❌ [TOOL] update_notebook failed: ${errorMessage}`);
      return {
        success: false,
        error: errorMessage,
      };
    }
  }

  /**
   * Handle remove_notebook tool
   */
  async handleRemoveNotebook(args: {
    id: string;
  }): Promise<ToolResult<{ removed: boolean; closed_sessions: number }>> {
    log.info(`🔧 [TOOL] remove_notebook called`);
    log.info(`  ID: ${args.id}`);

    try {
      const notebook = this.library.getNotebook(args.id);
      if (!notebook) {
        log.warning(`⚠️  [TOOL] Notebook not found: ${args.id}`);
        return {
          success: false,
          error: `Notebook not found: ${args.id}`,
        };
      }

      const removed = this.library.removeNotebook(args.id);
      if (removed) {
        const closedSessions = await this.sessionManager.closeSessionsForNotebook(notebook.url);
        log.success(`✅ [TOOL] remove_notebook completed`);
        return {
          success: true,
          data: { removed: true, closed_sessions: closedSessions },
        };
      } else {
        log.warning(`⚠️  [TOOL] Notebook not found: ${args.id}`);
        return {
          success: false,
          error: `Notebook not found: ${args.id}`,
        };
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      log.error(`❌ [TOOL] remove_notebook failed: ${errorMessage}`);
      return {
        success: false,
        error: errorMessage,
      };
    }
  }

  /**
   * Handle search_notebooks tool
   */
  async handleSearchNotebooks(args: {
    query: string;
  }): Promise<ToolResult<{ notebooks: NotebookEntry[] }>> {
    log.info(`🔧 [TOOL] search_notebooks called`);
    log.info(`  Query: "${args.query}"`);

    try {
      const notebooks = this.library.searchNotebooks(args.query);
      log.success(`✅ [TOOL] search_notebooks completed (${notebooks.length} results)`);
      return {
        success: true,
        data: { notebooks },
      };
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      log.error(`❌ [TOOL] search_notebooks failed: ${errorMessage}`);
      return {
        success: false,
        error: errorMessage,
      };
    }
  }

  /**
   * Handle get_library_stats tool
   */
  async handleGetLibraryStats(): Promise<ToolResult<LibraryStats>> {
    log.info(`🔧 [TOOL] get_library_stats called`);

    try {
      const stats = this.library.getStats();
      log.success(`✅ [TOOL] get_library_stats completed`);
      return {
        success: true,
        data: stats,
      };
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      log.error(`❌ [TOOL] get_library_stats failed: ${errorMessage}`);
      return {
        success: false,
        error: errorMessage,
      };
    }
  }

  /**
   * Handle cleanup_data tool
   *
   * ULTRATHINK Deep Cleanup - scans entire system for ALL NotebookLM MCP files
   */
  async handleCleanupData(args: { confirm: boolean; preserve_library?: boolean }): Promise<
    ToolResult<{
      status: string;
      mode: string;
      preview?: {
        categories: Array<{
          name: string;
          description: string;
          paths: string[];
          totalBytes: number;
          optional: boolean;
        }>;
        totalPaths: number;
        totalSizeBytes: number;
      };
      result?: {
        deletedPaths: string[];
        failedPaths: string[];
        totalSizeBytes: number;
        categorySummary: Record<string, { count: number; bytes: number }>;
      };
    }>
  > {
    const { confirm, preserve_library = false } = args;

    log.info(`🔧 [TOOL] cleanup_data called`);
    log.info(`  Confirm: ${confirm}`);
    log.info(`  Preserve Library: ${preserve_library}`);

    const cleanupManager = new CleanupManager();

    try {
      // Always run in deep mode
      const mode = "deep";

      if (!confirm) {
        // Preview mode - show what would be deleted
        log.info(`  📋 Generating cleanup preview (mode: ${mode})...`);

        const preview = await cleanupManager.getCleanupPaths(mode, preserve_library);
        const platformInfo = cleanupManager.getPlatformInfo();

        log.info(
          `  Found ${preview.totalPaths.length} items (${cleanupManager.formatBytes(preview.totalSizeBytes)})`
        );
        log.info(`  Platform: ${platformInfo.platform}`);

        return {
          success: true,
          data: {
            status: "preview",
            mode,
            preview: {
              categories: preview.categories,
              totalPaths: preview.totalPaths.length,
              totalSizeBytes: preview.totalSizeBytes,
            },
          },
        };
      } else {
        // Cleanup mode - actually delete files
        log.info(`  🗑️  Performing cleanup (mode: ${mode})...`);

        const result = await cleanupManager.performCleanup(mode, preserve_library);

        if (result.success) {
          log.success(
            `✅ [TOOL] cleanup_data completed - deleted ${result.deletedPaths.length} items`
          );
        } else {
          log.warning(`⚠️  [TOOL] cleanup_data completed with ${result.failedPaths.length} errors`);
        }

        return {
          success: result.success,
          data: {
            status: result.success ? "completed" : "partial",
            mode,
            result: {
              deletedPaths: result.deletedPaths,
              failedPaths: result.failedPaths,
              totalSizeBytes: result.totalSizeBytes,
              categorySummary: result.categorySummary,
            },
          },
        };
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      log.error(`❌ [TOOL] cleanup_data failed: ${errorMessage}`);
      return {
        success: false,
        error: errorMessage,
      };
    }
  }

  /**
   * Resolve a notebook URL the same way `handleAskQuestion` does. Used by the
   * new source/audio tools so we don't duplicate the lookup logic.
   */
  private async resolveNotebookUrl(
    notebookId?: string,
    notebookUrl?: string
  ): Promise<string | undefined> {
    if (notebookUrl) return notebookUrl;
    if (notebookId) {
      const nb = this.library.getNotebook(notebookId);
      if (!nb) throw new Error(`Notebook not found in library: ${notebookId}`);
      return nb.url;
    }
    const active = this.library.getActiveNotebook();
    return active?.url;
  }

  /**
   * Handle add_source tool (issue #25).
   */
  async handleAddSource(args: {
    type: "url" | "text";
    content: string;
    title?: string;
    session_id?: string;
    notebook_id?: string;
    notebook_url?: string;
    show_browser?: boolean;
  }): Promise<ToolResult<{ result: AddSourceResult }>> {
    log.info(`🔧 [TOOL] add_source called (type=${args.type})`);
    const originalConfig = { ...CONFIG };
    if (args.show_browser !== undefined) {
      const effectiveConfig = applyBrowserOptions(undefined, args.show_browser);
      Object.assign(CONFIG, effectiveConfig);
    }
    const overrideHeadless = args.show_browser === undefined ? undefined : args.show_browser;
    try {
      const url = await this.resolveNotebookUrl(args.notebook_id, args.notebook_url);
      const session = await this.sessionManager.getOrCreateSession(
        args.session_id,
        url,
        overrideHeadless
      );
      const result = await session.addSource({
        type: args.type,
        content: args.content,
        title: args.title,
      });
      return { success: result.success, data: { result } };
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      log.error(`❌ [TOOL] add_source failed: ${msg}`);
      return { success: false, error: msg };
    } finally {
      Object.assign(CONFIG, originalConfig);
    }
  }

  /**
   * Handle generate_audio tool (issue #11).
   */
  async handleGenerateAudio(args: {
    custom_prompt?: string;
    timeout_ms?: number;
    wait_for_completion?: boolean;
    session_id?: string;
    notebook_id?: string;
    notebook_url?: string;
    show_browser?: boolean;
  }): Promise<ToolResult<{ result: AudioGenerationResult }>> {
    log.info(`🔧 [TOOL] generate_audio called`);
    const originalConfig = { ...CONFIG };
    if (args.show_browser !== undefined) {
      Object.assign(CONFIG, applyBrowserOptions(undefined, args.show_browser));
    }
    const overrideHeadless = args.show_browser === undefined ? undefined : args.show_browser;
    try {
      const url = await this.resolveNotebookUrl(args.notebook_id, args.notebook_url);
      const session = await this.sessionManager.getOrCreateSession(
        args.session_id,
        url,
        overrideHeadless
      );
      const result = await session.generateAudio({
        customPrompt: args.custom_prompt,
        timeoutMs: args.timeout_ms,
        waitForCompletion: args.wait_for_completion ?? false,
      });
      // `started` and `in_progress` count as success — the generation is on
      // its way; the caller polls `get_audio_status` for completion.
      const ok =
        result.status === "ready" ||
        result.status === "started" ||
        result.status === "in_progress";
      return { success: ok, data: { result } };
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      log.error(`❌ [TOOL] generate_audio failed: ${msg}`);
      return { success: false, error: msg };
    } finally {
      Object.assign(CONFIG, originalConfig);
    }
  }

  /**
   * Handle get_audio_status tool — non-blocking poll for Audio Overview state.
   */
  async handleGetAudioStatus(args: {
    session_id?: string;
    notebook_id?: string;
    notebook_url?: string;
    show_browser?: boolean;
  }): Promise<ToolResult<{ result: AudioGenerationResult }>> {
    log.info(`🔧 [TOOL] get_audio_status called`);
    const originalConfig = { ...CONFIG };
    if (args.show_browser !== undefined) {
      Object.assign(CONFIG, applyBrowserOptions(undefined, args.show_browser));
    }
    const overrideHeadless = args.show_browser === undefined ? undefined : args.show_browser;
    try {
      const url = await this.resolveNotebookUrl(args.notebook_id, args.notebook_url);
      const session = await this.sessionManager.getOrCreateSession(
        args.session_id,
        url,
        overrideHeadless
      );
      const result = await session.getAudioStatus();
      return { success: true, data: { result } };
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      log.error(`❌ [TOOL] get_audio_status failed: ${msg}`);
      return { success: false, error: msg };
    } finally {
      Object.assign(CONFIG, originalConfig);
    }
  }

  /**
   * Handle download_audio tool (issue #11).
   */
  async handleDownloadAudio(args: {
    destination_dir: string;
    session_id?: string;
    notebook_id?: string;
    notebook_url?: string;
    show_browser?: boolean;
  }): Promise<ToolResult<{ result: DownloadAudioResult }>> {
    log.info(`🔧 [TOOL] download_audio called`);
    const originalConfig = { ...CONFIG };
    if (args.show_browser !== undefined) {
      Object.assign(CONFIG, applyBrowserOptions(undefined, args.show_browser));
    }
    const overrideHeadless = args.show_browser === undefined ? undefined : args.show_browser;
    try {
      const url = await this.resolveNotebookUrl(args.notebook_id, args.notebook_url);
      const session = await this.sessionManager.getOrCreateSession(
        args.session_id,
        url,
        overrideHeadless
      );
      const result = await session.downloadAudio(args.destination_dir);
      return { success: result.success, data: { result } };
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      log.error(`❌ [TOOL] download_audio failed: ${msg}`);
      return { success: false, error: msg };
    } finally {
      Object.assign(CONFIG, originalConfig);
    }
  }

  /**
   * Cleanup all resources (called on server shutdown)
   */
  async cleanup(): Promise<void> {
    log.info(`🧹 Cleaning up tool handlers...`);
    await this.sessionManager.closeAllSessions();
    log.success(`✅ Tool handlers cleanup complete`);
  }

  /**
   * 資料助秘：讀取 Google 帳號內 NotebookLM 首頁的筆記本清單（標題＋網址）。
   * 只讀取畫面，不會修改任何筆記本。
   */
  async handleListAccountNotebooks(args: { show_browser?: boolean }): Promise<
    ToolResult<{ notebooks: Array<{ title: string; url: string }> }>
  > {
    log.info("🔧 [TOOL] list_account_notebooks called");
    let page;
    try {
      const ctx = await this.sessionManager.getBrowserContext(
        args.show_browser === undefined ? undefined : !args.show_browser
      );
      page = await ctx.newPage();
      await page.goto("https://notebooklm.google.com/", { waitUntil: "domcontentloaded", timeout: 60000 });
      if (!/^https:\/\/notebook(lm)?\.google\.com\//.test(page.url())) {
        return { success: false, error: "尚未登入 Google（請先執行 setup_auth）" };
      }
      const deadline = Date.now() + 25000;
      let items: Array<{ title: string; url: string }> = [];
      while (Date.now() < deadline) {
        items = await page.evaluate(() => {
          const out: Array<{ title: string; url: string }> = [];
          const seen = new Set<string>();
          const clean = (t: string) => t.replace(/\s+/g, " ").trim();
          document.querySelectorAll('a[href*="/notebook/"]').forEach((a) => {
            const href = (a as HTMLAnchorElement).href.split("?")[0];
            if (seen.has(href)) return;
            seen.add(href);
            const box = a.closest("mat-card, project-button, tr, [role=row], div") || a;
            const tEl = box.querySelector(".project-button-title, .title, h3, [class*=title]");
            out.push({ title: clean((tEl && tEl.textContent) || a.textContent || ""), url: href });
          });
          // 新版首頁是卡片按鈕：從 aria-labelledby／id 裡找出筆記本 UUID
          document.querySelectorAll("project-button, mat-card, [role=button]").forEach((el) => {
            const html = el.outerHTML.slice(0, 4000);
            const m = html.match(/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/);
            if (!m) return;
            const href = location.origin + "/notebook/" + m[1];
            if (seen.has(href)) return;
            seen.add(href);
            const tEl = el.querySelector(".project-button-title, .title, h3, [class*=title]");
            out.push({ title: clean((tEl && tEl.textContent) || el.textContent || "").slice(0, 120), url: href });
          });
          return out;
        });
        if (items.length) break;
        await page.waitForTimeout(1500);
      }
      return { success: true, data: { notebooks: items } };
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      log.error(`❌ [TOOL] list_account_notebooks failed: ${msg}`);
      return { success: false, error: msg };
    } finally {
      try {
        await page?.close();
      } catch {
        /* ignore */
      }
    }
  }


  /**
   * 資料助秘：精簡版提問（新版 notebook.google.com 實測可用）。
   * 開一個新分頁 → 記下回答數 → 填入問題按 Enter → 等新回答出現且連續 3 次內容不變 → 取文字與引用來源名稱 → 關分頁。
   */
  async handleAskNotebook(
    args: { notebook_url: string; question: string; timeout_ms?: number; show_browser?: boolean },
    sendProgress?: ProgressCallback
  ): Promise<ToolResult<{ answer: string; sources: Array<{ index: number; title: string }>; seconds: number }>> {
    const t0 = Date.now();
    const timeout = Math.max(30_000, args.timeout_ms ?? 600_000);
    let page;
    try {
      const ctx = await this.sessionManager.getBrowserContext(
        args.show_browser === undefined ? undefined : !args.show_browser
      );
      page = await ctx.newPage();
      await sendProgress?.("Opening notebook...", 1, 5);
      await page.goto(args.notebook_url, { waitUntil: "domcontentloaded", timeout: 60_000 });
      if (!/^https:\/\/notebook(lm)?\.google\.com\/notebook\//.test(page.url())) {
        return { success: false, error: "無法開啟筆記本（可能尚未登入或沒有權限）：" + page.url() };
      }
      const box = page.locator("textarea.query-box-input").first();
      await box.waitFor({ state: "visible", timeout: 60_000 });
      // 等對話歷史載入完成（回答數連續 2 次相同）
      let prior = -1;
      for (let i = 0; i < 12; i++) {
        const n = await page.locator(".to-user-container").count();
        if (n === prior) break;
        prior = n;
        await page.waitForTimeout(1500);
      }
      await sendProgress?.("Submitting question...", 2, 5);
      await box.click();
      await box.fill(args.question);
      await page.waitForTimeout(400);
      await page.keyboard.press("Enter");
      await sendProgress?.("Waiting for NotebookLM answer...", 3, 5);
      const deadline = Date.now() + timeout;
      let last = "";
      let stable = 0;
      let answer = "";
      while (Date.now() < deadline) {
        await page.waitForTimeout(1500);
        const state = await page.evaluate((priorCount: number) => {
          const all = document.querySelectorAll(".to-user-container");
          if (all.length <= priorCount) return { n: all.length, text: "" };
          const el = all[all.length - 1].querySelector(".message-text-content") || all[all.length - 1];
          return { n: all.length, text: (el as HTMLElement).innerText || "" };
        }, prior);
        // 去掉 Material 圖示名稱（expand_more、more_vert…）單獨一行的雜訊
        const text = (state.text || "")
          .split(/\r?\n/)
          .filter((ln) => !/^\s*[a-z]+(_[a-z]+)+\s*$/.test(ln))
          .join("\n")
          .trim();
        // 思考中的狀態列（「正在剖析資料...」「已搜尋你的來源...」）不算回答
        const placeholder = !text || (text.length < 60 && /(\.\.\.|…)\s*$/.test(text));
        if (placeholder) {
          stable = 0;
          continue;
        }
        // JSON 還沒收尾（括號未成對）時，NotebookLM 常在中途停頓 → 要等更久才算寫完
        const opens = (text.match(/[{[]/g) || []).length;
        const closes = (text.match(/[}\]]/g) || []).length;
        const unfinished = /^\s*(```json\s*)?[{[]/.test(text) && opens > closes;
        if (text === last) {
          stable++;
          if (stable >= (unfinished ? 16 : 3)) {
            answer = text;
            break;
          }
        } else {
          last = text;
          stable = 0;
        }
      }
      if (!answer) {
        return { success: false, error: "等待 NotebookLM 回答逾時" + (last ? "（已收到部分內容）" : "") };
      }
      // 引用來源：側欄的來源名稱（依顯示順序編號）
      const sources = await page
        .evaluate(() =>
          Array.from(document.querySelectorAll(".single-source-container"))
            .map((el, i) => ({
              index: i + 1,
              title: ((el.querySelector(".source-title, [class*=title]") || el) as HTMLElement).innerText
                .replace(/\s+/g, " ")
                .replace(/^(article|description|picture_as_pdf|web|youtube_activity|drive_pdf|text_snippet)\s*/i, "")
                .trim()
                .slice(0, 160),
            }))
            .filter((s) => s.title)
        )
        .catch(() => []);
      await sendProgress?.("Done", 5, 5);
      return { success: true, data: { answer, sources, seconds: Math.round((Date.now() - t0) / 1000) } };
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      log.error(`❌ [TOOL] ask_notebook failed: ${msg}`);
      return { success: false, error: msg };
    } finally {
      try {
        await page?.close();
      } catch {
        /* ignore */
      }
    }
  }

}
