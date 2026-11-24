"""測試用：假的 NotebookLM 回答（NB_MCP_MOCK=1 時使用），格式與真的一樣是一段 JSON 文字。"""
import json


def mock_answer(question):
    q = question or ""
    if "投影片" in q or "簡報" in q:
        data = {"slides": [{"label": "封面頁", "title": "（會被專案封面取代）", "points": []}] + [
            {"label": "第 %d 頁" % i, "title": "測試投影片 %d" % i, "points": ["重點甲 [1]", "重點乙"],
             "notes": "講者備註 %d" % i} for i in range(2, 12)],
            "qa": [{"q": "測試題 %d？" % i, "a": "答案 %d" % i} for i in range(1, 6)]}
    elif "心智圖" in q:
        data = {"root": {"text": "測試主題", "children": [{"text": "分支 %d" % i, "children": [
            {"text": "子項 %d-%d" % (i, j)} for j in range(1, 4)]} for i in range(1, 6)]}}
    elif "報告" in q:
        data = {"title": "測試報告", "summary": "摘要。", "sections": [
            {"heading": "第 %d 節" % i, "paragraphs": ["段落內容。"], "bullets": ["重點一", "重點二"]} for i in range(1, 5)],
            "conclusion": "結論。", "references": ["範例來源.pdf"]}
    elif "測驗" in q:
        data = {"title": "測試測驗", "questions": [
            {"type": "single", "q": "單選題 %d？" % i, "options": ["A. 甲", "B. 乙", "C. 丙", "D. 丁"], "answer": "B",
             "explain": "因為乙。"} for i in range(1, 8)] + [
            {"type": "tf", "q": "是非題 %d" % i, "options": ["○", "✕"], "answer": "✕", "explain": "錯。"} for i in range(1, 4)]}
    elif "互動式學習網頁" in q:
        data = {"title": "測試網頁", "subtitle": "副標", "intro": "介紹", "sections": [
            {"heading": "第 %d 章" % i, "summary": "摘要", "points": ["甲", "乙"], "detail": "補充"} for i in range(1, 5)],
            "cards": [{"front": "詞 %d" % i, "back": "解釋"} for i in range(6)],
            "faq": [{"q": "問？", "a": "答。"}],
            "quiz": [{"q": "題？", "options": ["一", "二", "三"], "answer": "B", "explain": "因為二"}], "takeaway": "記住"}
    else:
        data = {"title": "測試資訊圖表", "subtitle": "一句話", "stats": [{"value": "3", "label": "個重點"}],
                "sections": [{"heading": "區塊 %d" % i, "points": ["重點一", "重點二"]} for i in range(1, 5)],
                "tip": "記得洗手", "footer": "測試"}
    return "以下是依來源整理的內容：\n```json\n%s\n```" % json.dumps(data, ensure_ascii=False)
