// 開發用：送出一個問題，每 2 秒記錄對話區的變化（使用 MCP 已登入的設定檔；MCP 不能同時執行）
import { chromium } from "patchright";
const profile = process.env.LOCALAPPDATA + "\\notebooklm-mcp\\Data\\chrome_profile";
const url = process.argv[2];
const ctx = await chromium.launchPersistentContext(profile, { channel: "chrome", headless: true, viewport: { width: 1400, height: 1000 } });
const page = await ctx.newPage();
await page.goto(url, { waitUntil: "domcontentloaded" });
await page.waitForTimeout(6000);
const snap = () => page.evaluate(() => {
  const q = (s) => document.querySelectorAll(s).length;
  const tu = [...document.querySelectorAll(".to-user-container")];
  const last = tu.length ? tu[tu.length - 1].innerText.replace(/\s+/g, " ").slice(0, 90) : "";
  const pairs = q(".chat-message-pair");
  const lastPair = document.querySelector(".chat-message-pair:last-of-type");
  return { toUser: tu.length, fromUser: q(".from-user-container"), pairs, last,
    lastPairText: lastPair ? lastPair.innerText.replace(/\s+/g, " ").slice(0, 120) : "",
    scroll: (document.querySelector(".chat-panel-content") || {}).scrollHeight };
});
console.log("before", JSON.stringify(await snap()));
const box = page.locator("textarea.query-box-input").first();
await box.fill("用一句話說明這本筆記本的主題。");
await page.waitForTimeout(500);
await page.keyboard.press("Enter");
for (let i = 0; i < 25; i++) {
  await page.waitForTimeout(2000);
  console.log(i * 2 + 2, JSON.stringify(await snap()));
}
await page.screenshot({ path: "probe2.png" });
await ctx.close();
