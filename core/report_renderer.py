from __future__ import annotations

from typing import Any

from core.models import Candidate, DailyResult

import html as _html

import re as _re

class MarkdownReportRenderer:
    def render(self, result: DailyResult) -> str:
        lines: list[str] = [
            "# 每日選股報告",
            "",
            "## 摘要表格",
            "",
        ]
        lines.extend(
            self._render_vertical_table(
                [
                    ("日期", result.date),
                    ("產生時間", result.generated_at or "未提供"),
                    ("設定檔", result.profile_name or "未提供"),
                    ("使用者", result.profile_display_name or "未提供"),
                    ("策略", result.strategy),
                    ("動作", self._action_label(result.action)),
                    ("選股模式", result.selection_mode or "未提供"),
                    ("Consider 數量", len(result.eligible_candidates)),
                    ("Watch 數量", len(result.watch_only_candidates)),
                ]
            )
        )

        lines.extend([
            "",
            "## 今日結論",
            "",
        ])
        lines.extend(self._build_overview(result))

        if result.explanation:
            lines.extend([
                "",
                "## 中文說明",
                "",
            ])
            for paragraph in str(result.explanation).split("\n\n"):
                paragraph = paragraph.strip()
                if paragraph:
                    lines.append(paragraph)
                    lines.append("")
            if lines and lines[-1] == "":
                lines.pop()

        lines.extend([
            "",
            "## Consider 候選",
            "",
        ])
        if result.eligible_candidates:
            lines.extend(self._render_candidate_section(result.eligible_candidates, section_label="Consider"))
        else:
            lines.append("今天沒有 Consider 候選。")

        lines.extend([
            "",
            "## Watch 名單",
            "",
        ])
        if result.watch_only_candidates:
            lines.extend(self._render_candidate_section(result.watch_only_candidates, section_label="Watch"))
        else:
            lines.append("今天沒有額外的 Watch 名單。")

        lines.extend([
            "",
            "## 系統備註",
            "",
        ])
        if result.notes:
            lines.extend([f"- {note}" for note in result.notes])
        else:
            lines.append("- 無")

        return "\n".join(lines).strip() + "\n"

    @staticmethod
    def _action_label(action: str) -> str:
        return "可進一步研究" if action == "consider" else "先觀察"

    def _build_overview(self, result: DailyResult) -> list[str]:
        consider_count = len(result.eligible_candidates)
        watch_count = len(result.watch_only_candidates)
        if result.action == "consider" and consider_count:
            return [
                f"今天有 **{consider_count} 檔** 標的進入 Consider，另有 **{watch_count} 檔** 在 Watch 名單中。",
                "系統輸出屬於研究輔助，不代表直接買賣建議。",
            ]
        return [
            f"今天沒有標的進入 Consider，目前較偏向先觀察；Watch 名單共有 **{watch_count} 檔**。",
            "系統輸出屬於研究輔助，不代表直接買賣建議。",
        ]

    def _render_candidate_section(self, candidates: list[Candidate], section_label: str) -> list[str]:
        lines: list[str] = [
            f"### {section_label} 摘要表格",
            "",
        ]
        lines.extend(self._render_candidate_summary_table(candidates))
        lines.extend([
            "",
            f"### {section_label} 詳細說明",
            "",
        ])
        for index, candidate in enumerate(candidates, start=1):
            lines.extend(self._render_candidate_detail(candidate, index=index, section_label=section_label))
        if lines and lines[-1] == "":
            lines.pop()
        return lines

    def _render_candidate_summary_table(self, candidates: list[Candidate]) -> list[str]:
        rows: list[list[Any]] = [
            [
                "順位",
                "標的",
                "名稱",
                "類型",
                "市場",
                "分數",
                "LLM 判讀",
                "收盤價",
                "月營收 YoY%",
                "ROE%",
                "摘要",
            ]
        ]
        for index, candidate in enumerate(candidates, start=1):
            metrics = candidate.metrics or {}
            verdict = metrics.get("llm_verdict") or "未提供"
            confidence = metrics.get("llm_confidence")
            if isinstance(confidence, (int, float)):
                verdict = f"{verdict} ({confidence:.2f})"
            rows.append(
                [
                    index,
                    candidate.asset,
                    candidate.name,
                    candidate.asset_category or "未提供",
                    candidate.market,
                    f"{candidate.score:.4f}",
                    verdict,
                    self._fmt_number(metrics.get("latest_close")),
                    self._fmt_number(metrics.get("latest_revenue_yoy_percent")),
                    self._fmt_number(metrics.get("roe_percent")),
                    metrics.get("llm_summary") or "未提供",
                ]
            )
        return self._render_matrix_table(rows)

    def _render_candidate_detail(self, candidate: Candidate, index: int, section_label: str) -> list[str]:
        metrics = candidate.metrics or {}
        lines: list[str] = [
            f"#### {section_label} {index}｜{candidate.asset} {candidate.name}",
            "",
            "##### 個股摘要表",
            "",
        ]
        lines.extend(
            self._render_vertical_table(
                [
                    ("市場", candidate.market),
                    ("類型", candidate.asset_category or "未提供"),
                    ("產業", candidate.industry or "未提供"),
                    ("分數", f"{candidate.score:.4f}"),
                    ("LLM 判讀", self._format_llm_verdict(metrics)),
                    ("收盤價", self._fmt_number(metrics.get("latest_close"))),
                    ("均線", self._fmt_number(metrics.get("ma_value"))),
                    ("距均線", self._fmt_number(metrics.get("distance_from_ma"))),
                    ("月營收月份", metrics.get("revenue_latest_month") or "未提供"),
                    ("月營收 YoY%", self._fmt_number(metrics.get("latest_revenue_yoy_percent"))),
                    ("月營收 MoM%", self._fmt_number(metrics.get("latest_revenue_mom_percent"))),
                    ("連續年增月數", self._fmt_number(metrics.get("positive_yoy_streak_months"))),
                    ("ROE%", self._fmt_number(metrics.get("roe_percent"))),
                    ("毛利率%", self._fmt_number(metrics.get("gross_margin_percent"))),
                    ("營益率%", self._fmt_number(metrics.get("operating_margin_percent"))),
                ]
            )
        )

        summary = metrics.get("llm_summary")
        if summary:
            lines.extend([
                "",
                "##### LLM 摘要",
                "",
                summary,
            ])

        why_items = candidate.why or metrics.get("llm_bull_points") or []
        if why_items:
            lines.extend([
                "",
                "##### 主要理由",
                "",
            ])
            lines.extend([f"- {item}" for item in why_items])

        lines.extend([
            "",
            "##### 法人拆解表格",
            "",
        ])
        lines.extend(self._render_institutional_breakdown_table(metrics.get("institutional_breakdown", {})))

        risk_items = metrics.get("llm_bear_points") or candidate.risk or []
        if risk_items:
            lines.extend([
                "",
                "##### 風險與保留因素",
                "",
            ])
            lines.extend([f"- {item}" for item in risk_items])

        invalidation = metrics.get("llm_invalidation_conditions") or []
        if invalidation:
            lines.extend([
                "",
                "##### 失效條件",
                "",
            ])
            lines.extend([f"- {item}" for item in invalidation])

        lines.append("")
        return lines

    def _render_institutional_breakdown_table(self, breakdown: dict[str, Any]) -> list[str]:
        rows: list[list[Any]] = [["法人", "近 20 日買超天數", "累計買超", "最新一日買超", "觀察窗"]]
        order = ["foreign_investor", "investment_trust", "dealer"]
        for key in order:
            entry = breakdown.get(key)
            if not entry:
                continue
            rows.append(
                [
                    entry.get("label", key),
                    entry.get("positive_days", 0),
                    self._fmt_number(entry.get("total_net_buy", 0)),
                    self._fmt_number(entry.get("latest_net_buy", 0)),
                    entry.get("window_days", 0),
                ]
            )
        if len(rows) == 1:
            rows.append(["無資料", "-", "-", "-", "-"])
        return self._render_matrix_table(rows)

    def _render_vertical_table(self, rows: list[tuple[str, Any]]) -> list[str]:
        table_rows: list[list[Any]] = [["欄位", "內容"]]
        for key, value in rows:
            table_rows.append([key, value])
        return self._render_matrix_table(table_rows)

    def _render_matrix_table(self, rows: list[list[Any]]) -> list[str]:
        if not rows:
            return []
        header = rows[0]
        body = rows[1:]
        lines = [
            "| " + " | ".join(self._md_cell(cell) for cell in header) + " |",
            "| " + " | ".join("---" for _ in header) + " |",
        ]
        for row in body:
            padded_row = list(row) + [""] * max(0, len(header) - len(row))
            lines.append("| " + " | ".join(self._md_cell(cell) for cell in padded_row[: len(header)]) + " |")
        return lines

    def _format_llm_verdict(self, metrics: dict[str, Any]) -> str:
        verdict = metrics.get("llm_verdict")
        confidence = metrics.get("llm_confidence")
        if not verdict:
            return "未提供"
        if isinstance(confidence, (int, float)):
            return f"{verdict} ({confidence:.2f})"
        return str(verdict)

    @staticmethod
    def _md_cell(value: Any) -> str:
        text = MarkdownReportRenderer._fmt_number(value)
        return text.replace("|", "\\|").replace("\n", "<br>")

    @staticmethod
    def _fmt_number(value: Any) -> str:
        if value is None:
            return "未提供"
        if isinstance(value, bool):
            return "是" if value else "否"
        if isinstance(value, int):
            return str(value)
        if isinstance(value, float):
            return f"{value:.2f}"
        return str(value)


class HtmlReportRenderer:
    """Convert a DailyResult into a self-contained HTML file."""

    CSS = """
    body{font-family:system-ui,sans-serif;max-width:960px;margin:2rem auto;padding:0 1rem;
         background:#0d1117;color:#c9d1d9}
    h1,h2,h3,h4,h5{color:#58a6ff;margin-top:1.5rem}
    table{border-collapse:collapse;width:100%;margin:.5rem 0;font-size:.85rem}
    th{background:#161b22;color:#8b949e;text-align:left;padding:.4rem .6rem;
       border:1px solid #30363d}
    td{padding:.35rem .6rem;border:1px solid #21262d}
    tr:nth-child(even) td{background:#161b22}
    ul{padding-left:1.4rem}
    li{margin:.2rem 0}
    strong{color:#e6edf3}
    hr{border:0;border-top:1px solid #30363d;margin:1.5rem 0}
    .badge-consider{color:#3fb950} .badge-watch{color:#d29922}
    .badge-hold{color:#8b949e}
    pre{white-space:pre-wrap;word-break:break-word}
    """

    # ── markdown → HTML primitives ──────────────────────────────────────────

    @staticmethod
    def _esc(text: str) -> str:
        return _html.escape(str(text), quote=False)

    @classmethod
    def _md_to_html(cls, md: str) -> str:
        lines = md.split("\n")
        out: list[str] = []
        in_table = False
        in_list = False

        for raw in lines:
            line = raw.rstrip()

            # Table row
            if line.startswith("|"):
                cells = [c.strip() for c in line.strip("|").split("|")]
                # separator row (---|---)
                if all(_re.fullmatch(r":?-+:?", c) for c in cells if c):
                    if not in_table:
                        out.append("<table>")
                        # promote last <tr> to <thead>
                        if out and "<tr>" in out[-2]:
                            out[-2] = out[-2].replace("<tr>", "<thead><tr>").replace("</tr>", "</tr></thead><tbody>")
                    in_table = True
                    continue
                tag = "th" if not in_table else "td"
                row = "".join(f"<{tag}>{cls._esc(c)}</{tag}>" for c in cells)
                out.append(f"<tr>{row}</tr>")
                continue
            else:
                if in_table:
                    out.append("</tbody></table>")
                    in_table = False

            # List item
            if line.startswith("- "):
                if not in_list:
                    out.append("<ul>")
                    in_list = True
                content = cls._inline(line[2:])
                out.append(f"<li>{content}</li>")
                continue
            else:
                if in_list:
                    out.append("</ul>")
                    in_list = False

            # Headings
            m = _re.match(r"^(#{1,5})\s+(.*)", line)
            if m:
                level = len(m.group(1))
                out.append(f"<h{level}>{cls._inline(m.group(2))}</h{level}>")
                continue

            # HR
            if _re.fullmatch(r"[-*_]{3,}", line.strip()):
                out.append("<hr>")
                continue

            # Blank line
            if not line.strip():
                out.append("")
                continue

            out.append(f"<p>{cls._inline(line)}</p>")

        if in_table:
            out.append("</tbody></table>")
        if in_list:
            out.append("</ul>")
        return "\n".join(out)

    @classmethod
    def _inline(cls, text: str) -> str:
        text = cls._esc(text)
        # **bold**
        text = _re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        # `code`
        text = _re.sub(r"`(.+?)`", r"<code>\1</code>", text)
        return text

    # ── public API ───────────────────────────────────────────────────────────

    def render(self, result: "DailyResult", markdown_text: str) -> str:  # type: ignore[name-defined]
        body = self._md_to_html(markdown_text)
        action_cls = "badge-consider" if result.action == "consider" else "badge-hold"
        action_label = "可進一步研究" if result.action == "consider" else "先觀察"
        title = f"選股報告 {result.date} — {result.profile_display_name or result.profile_name or ''}"
        return (
            "<!DOCTYPE html>\n<html lang='zh-Hant'>\n<head>\n"
            f"<meta charset='utf-8'>\n<title>{_html.escape(title)}</title>\n"
            f"<style>{self.CSS}</style>\n</head>\n<body>\n"
            f"<h1>{_html.escape(title)}</h1>\n"
            f"<p>動作：<strong class='{action_cls}'>{action_label}</strong>"
            f" &nbsp;|&nbsp; Consider：{len(result.eligible_candidates)} 檔"
            f" &nbsp;|&nbsp; Watch：{len(result.watch_only_candidates)} 檔</p>\n"
            f"<hr>\n{body}\n</body>\n</html>\n"
        )