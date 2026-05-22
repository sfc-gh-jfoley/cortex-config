#!/usr/bin/env python3
"""Build Google Slides from a JSON specification.

Usage:
    python build_slides.py <presentation_id> <spec.json>

The spec.json defines slides, layouts, and content. See references/slides-api-patterns.md for schema.
"""
import argparse, json, re, sys
from datetime import datetime
from pathlib import Path
from utils import get_services_with_creds, batch, parse_md_links, display_len, estimate_body_h
from diagram_builder import build_diagram

def _load_docs_links():
    p = Path(__file__).parent.parent / "config" / "snowflake_docs_links.json"
    with open(p) as f:
        data = json.load(f)
    return {**data.get("account_usage_views", {}), **data.get("functions", {})}

SNOWFLAKE_VIEW_DOCS = _load_docs_links()
TEMPLATE_MARKERS = [
    "lorem ipsum", "template", "icons:", "do's and don'ts",
    "sample slides", "charts", "bonus tips", "layout,",
    "using this template", "importing slides", "don'ts",
    "platform graphics", "logos and icons", "reference architecture",
    "world map", "pie charts", "table example",
]


def _rgb(color_array):
    return {"red": color_array[0], "green": color_array[1], "blue": color_array[2]}


class SlideBuilder:
    def __init__(self, svc, drive_svc, pid, config=None):
        self.svc = svc
        self.drive_svc = drive_svc
        self.pid = pid
        self.reqs = []
        self.pres = None
        self.config = config or {}

    def refresh(self):
        self.pres = self.svc.presentations().get(presentationId=self.pid).execute()

    @property
    def pw(self):
        return self.pres["pageSize"]["width"]["magnitude"]

    @property
    def page_h(self):
        return self.pres["pageSize"]["height"]["magnitude"]

    def _r(self, req):
        self.reqs.append(req)

    def flush(self):
        if self.reqs:
            batch(self.svc, self.pid, self.reqs)
            self.reqs = []

    def get_phs(self):
        self.refresh()
        ph_map = {}
        for slide in self.pres["slides"]:
            sid = slide["objectId"]
            phs = {}
            for el in slide.get("pageElements", []):
                pt = el.get("shape", {}).get("placeholder", {}).get("type")
                if pt:
                    phs.setdefault(pt, []).append(el["objectId"])
            ph_map[sid] = phs
        return ph_map

    def get_ph(self, ph_map, sid, ptype, idx=0):
        ids = ph_map.get(sid, {}).get(ptype, [])
        return ids[idx] if idx < len(ids) else None

    def is_template_only(self):
        self.refresh()
        slides = self.pres.get("slides", [])
        if not slides:
            return True
        template_count = 0
        for slide in slides:
            texts = ""
            for el in slide.get("pageElements", []):
                for te in el.get("shape", {}).get("text", {}).get("textElements", []):
                    if "textRun" in te:
                        texts += te["textRun"]["content"].lower()
            if any(m in texts for m in TEMPLATE_MARKERS):
                template_count += 1
        return template_count >= len(slides) * 0.8

    def backup(self):
        today = datetime.now().strftime("%Y%m%d")
        file_meta = self.drive_svc.files().get(
            fileId=self.pid, fields="name,parents", supportsAllDrives=True
        ).execute()
        original_name = file_meta["name"]
        parent = file_meta.get("parents", [None])[0]
        query = f"name contains '{original_name}_bk{today}' and trashed=false"
        if parent:
            query += f" and '{parent}' in parents"
        existing = self.drive_svc.files().list(
            q=query, fields="files(name)",
            supportsAllDrives=True, includeItemsFromAllDrives=True,
        ).execute().get("files", [])
        seq = len(existing) + 1
        backup_name = f"{original_name}_bk{today}_{seq:03d}"
        body = {"name": backup_name}
        copied = self.drive_svc.files().copy(
            fileId=self.pid, body=body, supportsAllDrives=True
        ).execute()
        return backup_name, copied["id"]

    def delete_all_slides(self):
        self.refresh()
        ids = [s["objectId"] for s in self.pres.get("slides", [])]
        if ids:
            batch(self.svc, self.pid, [{"deleteObject": {"objectId": i}} for i in ids], 50)
        return len(ids)

    def create_slides(self, slides_spec, insertion_offset=0):
        reqs = []
        for idx, s in enumerate(slides_spec):
            reqs.append(
                {
                    "createSlide": {
                        "objectId": s["id"],
                        "insertionIndex": insertion_offset + idx,
                        "slideLayoutReference": {"layoutId": s["layoutId"]},
                    }
                }
            )
        batch(self.svc, self.pid, reqs)

    def text(self, oid, text, fs=14, bold=False):
        if not oid or not text:
            return
        font = self.config.get("fonts", {}).get("primary", "Arial")
        self._r({"insertText": {"objectId": oid, "text": text}})
        self._r(
            {
                "updateTextStyle": {
                    "objectId": oid,
                    "style": {
                        "fontFamily": font,
                        "fontSize": {"magnitude": fs, "unit": "PT"},
                        "bold": bold,
                    },
                    "textRange": {"type": "ALL"},
                    "fields": "fontFamily,fontSize,bold",
                }
            }
        )

    def textbox(self, sid, oid, text, x, y, w, h, fs=11, bold=False, color=None):
        font = self.config.get("fonts", {}).get("primary", "Arial")
        self._r(
            {
                "createShape": {
                    "objectId": oid,
                    "shapeType": "TEXT_BOX",
                    "elementProperties": {
                        "pageObjectId": sid,
                        "size": {
                            "width": {"magnitude": w, "unit": "EMU"},
                            "height": {"magnitude": h, "unit": "EMU"},
                        },
                        "transform": {
                            "scaleX": 1,
                            "scaleY": 1,
                            "translateX": x,
                            "translateY": y,
                            "unit": "EMU",
                        },
                    },
                }
            }
        )
        self._r({"insertText": {"objectId": oid, "text": text}})
        style = {
            "fontFamily": font,
            "fontSize": {"magnitude": fs, "unit": "PT"},
            "bold": bold,
        }
        fields = "fontFamily,fontSize,bold"
        if color:
            style["foregroundColor"] = {"opaqueColor": {"rgbColor": color}}
            fields += ",foregroundColor"
        self._r(
            {
                "updateTextStyle": {
                    "objectId": oid,
                    "style": style,
                    "textRange": {"type": "ALL"},
                    "fields": fields,
                }
            }
        )

    def body_textbox(self, sid, oid, text, x=450000, y=1100000, w=8200000, h=1500000, fs=10):
        font = self.config.get("fonts", {}).get("primary", "Arial")
        colors = self.config.get("colors", {})
        accent_color = _rgb(colors.get("accent", [0.831, 0.357, 0.565]))
        features = self.config.get("features", {})
        line_spacing = self.config.get("layout", {}).get("body_line_spacing", 115)

        lines = text.split("\n")
        processed_lines = []
        bullet_line_indices = []
        for li, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("• ") or stripped.startswith("- "):
                processed_lines.append(stripped[2:])
                bullet_line_indices.append(li)
            elif stripped.startswith("•") or stripped.startswith("-"):
                processed_lines.append(stripped[1:].lstrip())
                bullet_line_indices.append(li)
            else:
                processed_lines.append(line)

        raw_text = "\n".join(processed_lines)
        link_parsed_text, links = parse_md_links(raw_text)

        raw_lines = link_parsed_text.split("\n")
        header_line_indices = set()
        md_heading_lines = set()
        for li, rline in enumerate(raw_lines):
            if li in bullet_line_indices:
                continue
            s = rline.strip()
            if not s:
                continue
            clean_s = re.sub(r'\*\*', '', s).strip()
            if clean_s.endswith(":") or clean_s.endswith(":\u200b"):
                header_line_indices.add(li)
            elif re.match(r'^#{1,4}\s+', clean_s):
                header_line_indices.add(li)
                md_heading_lines.add(li)

        clean_text = link_parsed_text.replace("**", "").replace("`", "")
        clean_text = re.sub(r'^(#{1,4})\s+', '', clean_text, flags=re.MULTILINE)

        self._r(
            {
                "createShape": {
                    "objectId": oid,
                    "shapeType": "TEXT_BOX",
                    "elementProperties": {
                        "pageObjectId": sid,
                        "size": {
                            "width": {"magnitude": w, "unit": "EMU"},
                            "height": {"magnitude": h, "unit": "EMU"},
                        },
                        "transform": {
                            "scaleX": 1,
                            "scaleY": 1,
                            "translateX": x,
                            "translateY": y,
                            "unit": "EMU",
                        },
                    },
                }
            }
        )
        self._r({"insertText": {"objectId": oid, "text": clean_text}})

        body_header_fs = self.config.get("sizes", {}).get("body_header", fs + 1)
        body_text_color = _rgb(colors.get("body_text", [0, 0, 0]))

        self._r(
            {
                "updateTextStyle": {
                    "objectId": oid,
                    "style": {
                        "fontFamily": font,
                        "fontSize": {"magnitude": fs, "unit": "PT"},
                        "bold": False,
                        "foregroundColor": {"opaqueColor": {"rgbColor": body_text_color}},
                    },
                    "textRange": {"type": "ALL"},
                    "fields": "fontFamily,fontSize,bold,foregroundColor",
                }
            }
        )

        clean_lines = clean_text.split("\n")
        offset = 0
        for li, line in enumerate(clean_lines):
            line_len = len(line) + 1
            if li in header_line_indices:
                stripped = line.strip()
                end_idx = offset + len(line.rstrip())
                start_idx = offset + (len(line) - len(line.lstrip()))
                if end_idx > start_idx:
                    self._r(
                        {
                            "updateTextStyle": {
                                "objectId": oid,
                                "style": {
                                    "bold": True,
                                    "fontSize": {"magnitude": body_header_fs, "unit": "PT"},
                                },
                                "textRange": {
                                    "type": "FIXED_RANGE",
                                    "startIndex": start_idx,
                                    "endIndex": end_idx,
                                },
                                "fields": "bold,fontSize",
                            }
                        }
                    )
            offset += line_len

        if bullet_line_indices:
            bullet_offset = 0
            for li, line in enumerate(clean_lines):
                line_len = len(line) + 1
                if li in bullet_line_indices:
                    self._r(
                        {
                            "createParagraphBullets": {
                                "objectId": oid,
                                "textRange": {
                                    "type": "FIXED_RANGE",
                                    "startIndex": bullet_offset,
                                    "endIndex": bullet_offset + line_len - 1,
                                },
                                "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
                            }
                        }
                    )
                bullet_offset += line_len

        self._r({
            "updateParagraphStyle": {
                "objectId": oid,
                "style": {"lineSpacing": line_spacing},
                "textRange": {"type": "ALL"},
                "fields": "lineSpacing",
            }
        })

        orig_offset = 0
        clean_offset = 0
        i = 0
        lp_lines_for_emph = link_parsed_text.split("\n")
        heading_skip = {}
        line_start_pos = 0
        for li_e, lp_line_e in enumerate(lp_lines_for_emph):
            hm_e = re.match(r'^#{1,4}\s+', lp_line_e)
            if hm_e:
                heading_skip[line_start_pos] = len(hm_e.group(0))
            line_start_pos += len(lp_line_e) + 1
        while i < len(link_parsed_text):
            if i in heading_skip:
                i += heading_skip[i]
                continue
            if link_parsed_text[i:i+2] == "**":
                i += 2
                end_marker = link_parsed_text.find("**", i)
                if end_marker == -1:
                    break
                emph_text = link_parsed_text[i:end_marker]
                emph_clean = emph_text.replace("`", "")
                emph_start = clean_offset
                emph_end = clean_offset + len(emph_clean)
                if features.get("body_accent_emphasis", True):
                    self._r(
                        {
                            "updateTextStyle": {
                                "objectId": oid,
                                "style": {
                                    "bold": True,
                                    "foregroundColor": {
                                        "opaqueColor": {"rgbColor": accent_color}
                                    },
                                },
                                "textRange": {
                                    "type": "FIXED_RANGE",
                                    "startIndex": emph_start,
                                    "endIndex": emph_end,
                                },
                                "fields": "bold,foregroundColor",
                            }
                        }
                    )
                else:
                    self._r(
                        {
                            "updateTextStyle": {
                                "objectId": oid,
                                "style": {"bold": True},
                                "textRange": {
                                    "type": "FIXED_RANGE",
                                    "startIndex": emph_start,
                                    "endIndex": emph_end,
                                },
                                "fields": "bold",
                            }
                        }
                    )
                clean_offset += len(emph_clean)
                i = end_marker + 2
            elif link_parsed_text[i] == "`":
                i += 1
                end_marker = link_parsed_text.find("`", i)
                if end_marker == -1:
                    remaining = link_parsed_text[i:]
                    clean_offset += len(remaining)
                    break
                code_text = link_parsed_text[i:end_marker]
                code_start = clean_offset
                code_end = clean_offset + len(code_text)
                if code_end > code_start:
                    style = {"bold": True}
                    fields = "bold"
                    if features.get("auto_link_snowflake_views", True):
                        doc_url = SNOWFLAKE_VIEW_DOCS.get(code_text.strip().upper())
                        if doc_url:
                            style["link"] = {"url": doc_url}
                            fields += ",link"
                    self._r(
                        {
                            "updateTextStyle": {
                                "objectId": oid,
                                "style": style,
                                "textRange": {
                                    "type": "FIXED_RANGE",
                                    "startIndex": code_start,
                                    "endIndex": code_end,
                                },
                                "fields": fields,
                            }
                        }
                    )
                clean_offset += len(code_text)
                i = end_marker + 1
            else:
                clean_offset += 1
                i += 1

        if links:
            lp_lines = link_parsed_text.split("\n")
            heading_removed_per_line = []
            for lp_line in lp_lines:
                hm = re.match(r'^(#{1,4})\s+', lp_line)
                heading_removed_per_line.append(len(hm.group(0)) if hm else 0)

            def _count_removed_before(text, pos):
                removed = 0
                line_idx = 0
                line_start = 0
                for li, lp_line in enumerate(lp_lines):
                    line_end = line_start + len(lp_line) + (1 if li < len(lp_lines) - 1 else 0)
                    if pos <= line_end:
                        line_idx = li
                        break
                    line_start = line_end
                    line_idx = li
                for li in range(line_idx + 1):
                    removed += heading_removed_per_line[li]
                i = 0
                while i < pos:
                    if text[i:i+2] == "**":
                        removed += 2
                        i += 2
                    elif text[i] == "`":
                        removed += 1
                        i += 1
                    else:
                        i += 1
                return removed

            for start, end, url in links:
                clean_start = start - _count_removed_before(link_parsed_text, start)
                clean_end = end - _count_removed_before(link_parsed_text, end)
                if clean_end > clean_start:
                    self._r({
                        "updateTextStyle": {
                            "objectId": oid,
                            "style": {
                                "link": {"url": url},
                            },
                            "textRange": {
                                "type": "FIXED_RANGE",
                                "startIndex": clean_start,
                                "endIndex": clean_end,
                            },
                            "fields": "link",
                        }
                    })

        if features.get("auto_link_snowflake_views", True):
            for view_name, doc_url in SNOWFLAKE_VIEW_DOCS.items():
                if len(view_name) < 10:
                    continue
                for m in re.finditer(r'\b' + re.escape(view_name) + r'\b', clean_text):
                    self._r({
                        "updateTextStyle": {
                            "objectId": oid,
                            "style": {"link": {"url": doc_url}},
                            "textRange": {
                                "type": "FIXED_RANGE",
                                "startIndex": m.start(),
                                "endIndex": m.end(),
                            },
                            "fields": "link",
                        }
                    })

    @staticmethod
    def _auto_column_widths(data, table_w, fs, min_col_w=500000):
        nc = len(data[0])

        def _display_width(text):
            if not text:
                return 1
            text = str(text)
            text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
            text = text.replace("**", "").replace("`", "")
            lines = text.split("\n")
            max_w = 0
            for line in lines:
                w = 0
                for ch in line:
                    if '\u3000' <= ch <= '\u9fff' or '\uf900' <= ch <= '\ufaff' or '\uff00' <= ch <= '\uffef':
                        w += 2
                    elif '\uac00' <= ch <= '\ud7af':
                        w += 2
                    else:
                        w += 1
                max_w = max(max_w, w)
            return max(max_w, 1)

        col_max = [0] * nc
        for row in data:
            for ci, cell in enumerate(row):
                col_max[ci] = max(col_max[ci], _display_width(cell))

        total = sum(col_max)
        if total == 0:
            return None

        widths = [max(int(table_w * (cm / total)), min_col_w) for cm in col_max]

        diff = table_w - sum(widths)
        if diff != 0:
            widest = widths.index(max(widths))
            widths[widest] += diff

        return widths

    def table(self, sid, oid, data, x=450000, y=1700000, w=8200000, rh=330000, fs=8, column_widths=None):
        font = self.config.get("fonts", {}).get("primary", "Arial")
        code_font = self.config.get("fonts", {}).get("code", "Courier New")
        colors = self.config.get("colors", {})
        table_cfg = self.config.get("table", {})
        features = self.config.get("features", {})
        snowflake_blue = _rgb(colors.get("snowflake_blue", [0.16, 0.71, 0.91]))
        bg_color = _rgb(table_cfg.get("background_color", [0.92, 0.97, 1.0]))
        zebra_color = _rgb(table_cfg.get("background_zebra_color", [0.86, 0.94, 0.99]))
        border_color = _rgb(table_cfg.get("border_color", [1, 1, 1]))
        min_col_w = table_cfg.get("min_column_width", 500000)
        table_header_increment = self.config.get("sizes", {}).get("table_header_increment", 1)
        jp_period = features.get("jp_period_to_newline", True)
        zebra_stripes = features.get("table_zebra_stripes", True)

        nr, nc = len(data), len(data[0])
        h = rh * nr

        if not column_widths and nc > 1:
            column_widths = self._auto_column_widths(data, w, fs, min_col_w)

        self._r(
            {
                "createTable": {
                    "objectId": oid,
                    "rows": nr,
                    "columns": nc,
                    "elementProperties": {
                        "pageObjectId": sid,
                        "size": {
                            "width": {"magnitude": w, "unit": "EMU"},
                            "height": {"magnitude": h, "unit": "EMU"},
                        },
                        "transform": {
                            "scaleX": 1,
                            "scaleY": 1,
                            "translateX": x,
                            "translateY": y,
                            "unit": "EMU",
                        },
                    },
                }
            }
        )
        if column_widths:
            for ci, cw in enumerate(column_widths):
                if ci < nc:
                    self._r(
                        {
                            "updateTableColumnProperties": {
                                "objectId": oid,
                                "columnIndices": [ci],
                                "tableColumnProperties": {
                                    "columnWidth": {"magnitude": max(cw, 406400), "unit": "EMU"}
                                },
                                "fields": "columnWidth",
                            }
                        }
                    )
        deferred_bold = []
        deferred_code = []
        for ri, row in enumerate(data):
            for ci, v in enumerate(row):
                if v:
                    cell_text = str(v)
                    cell_text, cell_links = parse_md_links(cell_text)
                    if ri > 0 and jp_period and "。" in cell_text:
                        cell_text = cell_text.replace("。", "\n")
                        if cell_text.endswith("\n"):
                            cell_text = cell_text[:-1]
                    bold_ranges = []
                    code_ranges = []
                    clean_cell_text = ""
                    pos = 0
                    has_markup = False
                    removed_ranges = []
                    while pos < len(cell_text):
                        next_bold = cell_text.find("**", pos)
                        next_code = cell_text.find("`", pos)
                        if next_bold == -1 and next_code == -1:
                            clean_cell_text += cell_text[pos:]
                            break
                        if next_bold != -1 and (next_code == -1 or next_bold <= next_code):
                            clean_cell_text += cell_text[pos:next_bold]
                            end_marker = cell_text.find("**", next_bold + 2)
                            if end_marker == -1:
                                clean_cell_text += cell_text[next_bold:]
                                break
                            removed_ranges.append((next_bold, next_bold + 2))
                            inner = cell_text[next_bold + 2:end_marker]
                            inner_clean = ""
                            ci_inner = next_bold + 2
                            for ch in inner:
                                if ch == "`":
                                    removed_ranges.append((ci_inner, ci_inner + 1))
                                else:
                                    inner_clean += ch
                                ci_inner += 1
                            bold_start = len(clean_cell_text)
                            clean_cell_text += inner_clean
                            bold_ranges.append((bold_start, bold_start + len(inner_clean)))
                            removed_ranges.append((end_marker, end_marker + 2))
                            has_markup = True
                            pos = end_marker + 2
                        else:
                            clean_cell_text += cell_text[pos:next_code]
                            end_marker = cell_text.find("`", next_code + 1)
                            if end_marker == -1:
                                clean_cell_text += cell_text[next_code:]
                                break
                            removed_ranges.append((next_code, next_code + 1))
                            code_start = len(clean_cell_text)
                            code_text = cell_text[next_code + 1:end_marker]
                            clean_cell_text += code_text
                            code_ranges.append((code_start, code_start + len(code_text)))
                            removed_ranges.append((end_marker, end_marker + 1))
                            has_markup = True
                            pos = end_marker + 1
                    if not has_markup:
                        clean_cell_text = cell_text
                    self._r(
                        {
                            "insertText": {
                                "objectId": oid,
                                "cellLocation": {"rowIndex": ri, "columnIndex": ci},
                                "text": clean_cell_text,
                            }
                        }
                    )
                    if bold_ranges:
                        deferred_bold.append((ri, ci, bold_ranges))
                    if code_ranges:
                        deferred_code.append((ri, ci, code_ranges))
                    if cell_links:
                        def _adj(orig_pos):
                            removed = 0
                            for rs, re_ in removed_ranges:
                                if rs < orig_pos:
                                    removed += min(re_, orig_pos) - rs
                            return orig_pos - removed
                        for link_start, link_end, link_url in cell_links:
                            adj_start = _adj(link_start)
                            adj_end = _adj(link_end)
                            if adj_end > adj_start:
                                self._r({
                                    "updateTextStyle": {
                                        "objectId": oid,
                                        "cellLocation": {"rowIndex": ri, "columnIndex": ci},
                                        "style": {"link": {"url": link_url}},
                                        "textRange": {
                                            "type": "FIXED_RANGE",
                                            "startIndex": adj_start,
                                            "endIndex": adj_end,
                                        },
                                        "fields": "link",
                                    }
                                })
                    if ri > 0 and "\n" in cell_text:
                        self._r(
                            {
                                "createParagraphBullets": {
                                    "objectId": oid,
                                    "cellLocation": {"rowIndex": ri, "columnIndex": ci},
                                    "textRange": {"type": "ALL"},
                                    "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
                                }
                            }
                        )
                        self._r(
                            {
                                "updateParagraphStyle": {
                                    "objectId": oid,
                                    "cellLocation": {"rowIndex": ri, "columnIndex": ci},
                                    "style": {
                                        "indentFirstLine": {"magnitude": 54864, "unit": "EMU"},
                                        "indentStart": {"magnitude": 173736, "unit": "EMU"},
                                    },
                                    "textRange": {"type": "ALL"},
                                    "fields": "indentFirstLine,indentStart",
                                }
                            }
                        )
        self._r(
            {
                "updateTableCellProperties": {
                    "objectId": oid,
                    "tableRange": {
                        "location": {"rowIndex": 0, "columnIndex": 0},
                        "rowSpan": 1,
                        "columnSpan": nc,
                    },
                    "tableCellProperties": {
                        "tableCellBackgroundFill": {
                            "solidFill": {"color": {"rgbColor": snowflake_blue}}
                        }
                    },
                    "fields": "tableCellBackgroundFill.solidFill.color",
                }
            }
        )
        for ri in range(1, nr):
            if zebra_stripes:
                bg = zebra_color if ri % 2 == 1 else bg_color
            else:
                bg = bg_color
            self._r(
                {
                    "updateTableCellProperties": {
                        "objectId": oid,
                        "tableRange": {
                            "location": {"rowIndex": ri, "columnIndex": 0},
                            "rowSpan": 1,
                            "columnSpan": nc,
                        },
                        "tableCellProperties": {
                            "tableCellBackgroundFill": {
                                "solidFill": {"color": {"rgbColor": bg}}
                            }
                        },
                        "fields": "tableCellBackgroundFill.solidFill.color",
                    }
                }
            )
        WHITE_BORDER = {
            "tableBorderFill": {"solidFill": {"color": {"rgbColor": border_color}}},
            "weight": {"magnitude": 1, "unit": "PT"},
            "dashStyle": "SOLID",
        }
        for ri in range(nr):
            for pos in ("TOP", "BOTTOM"):
                self._r(
                    {
                        "updateTableBorderProperties": {
                            "objectId": oid,
                            "tableRange": {
                                "location": {"rowIndex": ri, "columnIndex": 0},
                                "rowSpan": 1,
                                "columnSpan": nc,
                            },
                            "borderPosition": pos,
                            "tableBorderProperties": WHITE_BORDER,
                            "fields": "tableBorderFill,weight,dashStyle",
                        }
                    }
                )
        for ci in range(nc):
            for pos in ("LEFT", "RIGHT"):
                self._r(
                    {
                        "updateTableBorderProperties": {
                            "objectId": oid,
                            "tableRange": {
                                "location": {"rowIndex": 0, "columnIndex": ci},
                                "rowSpan": nr,
                                "columnSpan": 1,
                            },
                            "borderPosition": pos,
                            "tableBorderProperties": WHITE_BORDER,
                            "fields": "tableBorderFill,weight,dashStyle",
                        }
                    }
                )
        for ci in range(nc):
            if not data[0][ci]:
                continue
            self._r(
                {
                    "updateTextStyle": {
                        "objectId": oid,
                        "cellLocation": {"rowIndex": 0, "columnIndex": ci},
                        "style": {
                            "bold": True,
                            "fontSize": {"magnitude": fs + table_header_increment, "unit": "PT"},
                            "fontFamily": font,
                            "foregroundColor": {
                                "opaqueColor": {
                                    "rgbColor": {"red": 1, "green": 1, "blue": 1}
                                }
                            },
                        },
                        "textRange": {"type": "ALL"},
                        "fields": "bold,fontSize,fontFamily,foregroundColor",
                    }
                }
            )
        for ri in range(1, nr):
            for ci in range(nc):
                if not data[ri][ci]:
                    continue
                self._r(
                    {
                        "updateTextStyle": {
                            "objectId": oid,
                            "cellLocation": {"rowIndex": ri, "columnIndex": ci},
                            "style": {
                                "fontSize": {"magnitude": fs, "unit": "PT"},
                                "fontFamily": font,
                            },
                            "textRange": {"type": "ALL"},
                            "fields": "fontSize,fontFamily",
                        }
                    }
                )
        for ri, ci, bold_ranges in deferred_bold:
            for bs, be in bold_ranges:
                if be > bs:
                    self._r({
                        "updateTextStyle": {
                            "objectId": oid,
                            "cellLocation": {"rowIndex": ri, "columnIndex": ci},
                            "style": {"bold": True},
                            "textRange": {
                                "type": "FIXED_RANGE",
                                "startIndex": bs,
                                "endIndex": be,
                            },
                            "fields": "bold",
                        }
                    })
        for ri, ci, code_ranges in deferred_code:
            for cs, ce in code_ranges:
                if ce > cs:
                    self._r({
                        "updateTextStyle": {
                            "objectId": oid,
                            "cellLocation": {"rowIndex": ri, "columnIndex": ci},
                            "style": {"bold": True, "fontFamily": code_font},
                            "textRange": {
                                "type": "FIXED_RANGE",
                                "startIndex": cs,
                                "endIndex": ce,
                            },
                            "fields": "bold,fontFamily",
                        }
                    })

    def code(self, sid, oid, source, language="sql", x=450000, y=1700000, w=8200000, h=None, fs=8):
        from pygments import lex
        from pygments.lexers import get_lexer_by_name
        from pygments.token import Keyword, Name, String, Number, Comment, Operator, Punctuation, Error, Token

        colors = self.config.get("colors", {})
        code_block_cfg = self.config.get("code_block", {})
        snowflake_blue = _rgb(colors.get("snowflake_blue", [0.16, 0.71, 0.91]))
        code_bg = _rgb(colors.get("code_background", [0.051, 0.067, 0.09]))
        code_font = self.config.get("fonts", {}).get("code", "Courier New")
        ACCENT_BAR_W = code_block_cfg.get("accent_bar_width", 50000)
        PAD = code_block_cfg.get("padding", 80000)

        accent_colors_cfg = code_block_cfg.get("accent_colors", {})
        sql_accent = _rgb(accent_colors_cfg.get("sql", [0.16, 0.71, 0.91]))
        prog_accent = _rgb(accent_colors_cfg.get("programming", [0.494, 0.341, 0.761]))
        config_accent = _rgb(accent_colors_cfg.get("config", [0.545, 0.580, 0.620]))
        other_accent = _rgb(accent_colors_cfg.get("other", [0.306, 0.667, 0.145]))

        CODE_ACCENT_COLORS = {
            "sql": sql_accent,
            "python": prog_accent,
            "java": prog_accent,
            "javascript": prog_accent,
            "typescript": prog_accent,
            "go": prog_accent,
            "rust": prog_accent,
            "scala": prog_accent,
            "ruby": prog_accent,
            "json": config_accent,
            "yaml": config_accent,
            "toml": config_accent,
            "xml": config_accent,
            "ini": config_accent,
            "bash": other_accent,
            "shell": other_accent,
            "sh": other_accent,
            "text": other_accent,
        }
        accent_bar_color = CODE_ACCENT_COLORS.get(language.lower(), other_accent)

        DARK_THEME = {
            Keyword:              (0xFF, 0x7B, 0x72),
            Keyword.Constant:     (0x79, 0xC0, 0xFF),
            Keyword.Type:         (0xFF, 0xA6, 0x57),
            Name:                 (0xE6, 0xED, 0xF3),
            Name.Builtin:         (0x79, 0xC0, 0xFF),
            Name.Function:        (0xD2, 0xA8, 0xFF),
            Name.Other:           (0xD2, 0xA8, 0xFF),
            Name.Attribute:       (0x79, 0xC0, 0xFF),
            Name.Constant:        (0x79, 0xC0, 0xFF),
            Name.Decorator:       (0x79, 0xC0, 0xFF),
            Name.Tag:             (0x7E, 0xE7, 0x87),
            String:               (0xA5, 0xD6, 0xFF),
            String.Single:        (0xA5, 0xD6, 0xFF),
            Number:               (0x79, 0xC0, 0xFF),
            Number.Integer:       (0x79, 0xC0, 0xFF),
            Number.Float:         (0x79, 0xC0, 0xFF),
            Comment:              (0x8B, 0x94, 0x9E),
            Comment.Single:       (0x8B, 0x94, 0x9E),
            Comment.Multiline:    (0x8B, 0x94, 0x9E),
            Operator:             (0xFF, 0x7B, 0x72),
            Operator.Word:        (0x79, 0xC0, 0xFF),
            Punctuation:          (0xE6, 0xED, 0xF3),
            Error:                (0xFF, 0xA1, 0x98),
            Token.Text:           (0xE6, 0xED, 0xF3),
            Token:                (0xE6, 0xED, 0xF3),
        }
        DEFAULT_COLOR = (0xE6, 0xED, 0xF3)

        SNOWFLAKE_KEYWORDS = {
            "TABLES", "CORTEX", "LATERAL", "FLATTEN", "PIVOT", "UNPIVOT",
            "QUALIFY", "ILIKE", "RLIKE", "DYNAMIC", "ICEBERG", "HYBRID",
            "STAGE", "PIPE", "STREAM", "TASK", "SEQUENCE", "CLONE",
            "WAREHOUSE", "DATABASE", "SCHEMA", "ROLE", "GRANT", "REVOKE",
            "DESCRIBE", "SHOW", "ACCOUNT", "PROCEDURE", "FUNCTION",
            "TARGET_LAG", "REFRESH_MODE", "CHANGE_TRACKING",
            "AI_SQL_GENERATION", "SEMANTIC", "VIEW",
        }
        SNOWFLAKE_FUNCTIONS = {
            "ARRAY_AGG", "ARRAY_CONSTRUCT", "FLATTEN", "OBJECT_CONSTRUCT",
            "PARSE_JSON", "TO_JSON", "TO_VARIANT", "IFF", "IFNULL", "NVL",
            "COALESCE", "GREATEST", "LEAST", "MAX_BY", "MIN_BY", "ANY_VALUE",
            "LISTAGG", "RESULT_SCAN", "SYSTEM$STREAM_HAS_DATA",
            "DATE_TRUNC", "DATEADD", "DATEDIFF", "TRY_CAST", "TRY_TO_NUMBER",
            "LAST_VALUE", "FIRST_VALUE", "ROW_NUMBER", "RANK", "DENSE_RANK",
            "GET_DDL", "INFER_SCHEMA", "SEARCH", "CURRENT_TIMESTAMP",
        }

        def resolve_color(token_type):
            t = token_type
            while t is not None:
                if t in DARK_THEME:
                    return DARK_THEME[t]
                t = t.parent
            return DEFAULT_COLOR

        def reclassify(tokens):
            result = []
            for tok_type, value in tokens:
                upper = value.strip().upper()
                if upper in SNOWFLAKE_FUNCTIONS and tok_type in (Name, Keyword):
                    result.append((Name.Function, value))
                elif tok_type is Name and upper in SNOWFLAKE_KEYWORDS:
                    result.append((Keyword, value))
                else:
                    result.append((tok_type, value))
            return result

        lexer = get_lexer_by_name(language, stripall=False)
        raw_tokens = list(lex(source, lexer))
        tokens = reclassify(raw_tokens)

        lines = source.split("\n")
        if lines and lines[-1] == "":
            lines = lines[:-1]
        line_count = len(lines)
        line_h = int(fs * 914400 / 72 * 1.4)
        if h is None:
            h = line_count * line_h + PAD * 2
        total_h = h

        bg_id = f"{oid}_bg"
        accent_id = f"{oid}_acc"
        box_id = f"{oid}_txt"
        CODE_PAD_TOP = 60000
        CODE_PAD_LEFT = ACCENT_BAR_W + 80000
        CODE_PAD_RIGHT = 80000
        CODE_PAD_BOTTOM = 60000

        self._r({
            "createShape": {
                "objectId": bg_id, "shapeType": "RECTANGLE",
                "elementProperties": {
                    "pageObjectId": sid,
                    "size": {"width": {"magnitude": w, "unit": "EMU"}, "height": {"magnitude": h, "unit": "EMU"}},
                    "transform": {"scaleX": 1, "scaleY": 1, "translateX": x, "translateY": y, "unit": "EMU"},
                },
            }
        })
        self._r({"updateShapeProperties": {
            "objectId": bg_id,
            "shapeProperties": {
                "shapeBackgroundFill": {"solidFill": {"color": {"rgbColor": code_bg}}},
                "outline": {"propertyState": "NOT_RENDERED"},
            },
            "fields": "shapeBackgroundFill,outline",
        }})

        self._r({
            "createShape": {
                "objectId": accent_id, "shapeType": "RECTANGLE",
                "elementProperties": {
                    "pageObjectId": sid,
                    "size": {"width": {"magnitude": ACCENT_BAR_W, "unit": "EMU"}, "height": {"magnitude": total_h, "unit": "EMU"}},
                    "transform": {"scaleX": 1, "scaleY": 1, "translateX": x, "translateY": y, "unit": "EMU"},
                },
            }
        })
        self._r({"updateShapeProperties": {
            "objectId": accent_id,
            "shapeProperties": {
                "shapeBackgroundFill": {"solidFill": {"color": {"rgbColor": accent_bar_color}}},
                "outline": {"propertyState": "NOT_RENDERED"},
            },
            "fields": "shapeBackgroundFill,outline",
        }})

        text_x = x + CODE_PAD_LEFT
        text_y = y + CODE_PAD_TOP
        text_w = w - CODE_PAD_LEFT - CODE_PAD_RIGHT
        text_h = h - CODE_PAD_TOP - CODE_PAD_BOTTOM
        self._r({
            "createShape": {
                "objectId": box_id, "shapeType": "TEXT_BOX",
                "elementProperties": {
                    "pageObjectId": sid,
                    "size": {"width": {"magnitude": text_w, "unit": "EMU"}, "height": {"magnitude": text_h, "unit": "EMU"}},
                    "transform": {"scaleX": 1, "scaleY": 1, "translateX": text_x, "translateY": text_y, "unit": "EMU"},
                },
            }
        })

        full_text = "".join(value for _, value in tokens)
        self._r({"insertText": {"objectId": box_id, "text": full_text}})

        idx = 0
        for token_type, value in tokens:
            if not value:
                continue
            length = len(value)
            r, g, b = resolve_color(token_type)
            self._r({
                "updateTextStyle": {
                    "objectId": box_id,
                    "textRange": {"type": "FIXED_RANGE", "startIndex": idx, "endIndex": idx + length},
                    "style": {
                        "foregroundColor": {"opaqueColor": {"rgbColor": {"red": r / 255, "green": g / 255, "blue": b / 255}}},
                        "fontFamily": code_font,
                        "fontSize": {"magnitude": fs, "unit": "PT"},
                        "bold": True,
                    },
                    "fields": "foregroundColor,fontFamily,fontSize,bold",
                }
            })
            idx += length

    def hide_empty_placeholders(self):
        self.refresh()
        reqs = []
        count = 0
        for slide in self.pres["slides"]:
            for el in slide.get("pageElements", []):
                ph = el.get("shape", {}).get("placeholder")
                if not ph:
                    continue
                t = ""
                for te in el.get("shape", {}).get("text", {}).get("textElements", []):
                    if "textRun" in te:
                        t += te["textRun"]["content"]
                ph_type = ph.get("type", "")
                if ph_type == "SLIDE_NUMBER":
                    continue
                if not t.strip():
                    reqs.append(
                        {
                            "updatePageElementTransform": {
                                "objectId": el["objectId"],
                                "applyMode": "ABSOLUTE",
                                "transform": {
                                    "scaleX": 0.01,
                                    "scaleY": 0.01,
                                    "translateX": 20000000,
                                    "translateY": 20000000,
                                    "unit": "EMU",
                                },
                            }
                        }
                    )
                    count += 1
        if reqs:
            batch(self.svc, self.pid, reqs, 50)
        return count

    def verify(self):
        self.refresh()
        issues = []
        lmap = {
            l["objectId"]: l.get("layoutProperties", {}).get("displayName", "?")
            for l in self.pres.get("layouts", [])
        }
        for i, slide in enumerate(self.pres["slides"]):
            if slide.get("slideProperties", {}).get("isSkipped"):
                continue
            sid = slide["objectId"]
            for el in slide.get("pageElements", []):
                if "line" in el:
                    continue
                t = el.get("transform", {})
                s = el.get("size", {})
                tx = t.get("translateX", 0)
                ty = t.get("translateY", 0)
                if tx > 15000000:
                    continue
                w = s.get("width", {}).get("magnitude", 0) * t.get("scaleX", 1)
                h = s.get("height", {}).get("magnitude", 0) * t.get("scaleY", 1)
                if tx + w > self.pw + 100000:
                    issues.append(f"Slide {i+1} ({sid}): RIGHT overflow")
                if ty + h > self.page_h + 100000:
                    issues.append(f"Slide {i+1} ({sid}): BOTTOM overflow")
        return {
            "slideCount": len(self.pres["slides"]),
            "issues": issues,
            "slides": [
                {
                    "index": i + 1,
                    "objectId": s["objectId"],
                    "layout": lmap.get(
                        s.get("slideProperties", {}).get("layoutObjectId", ""), "?"
                    ),
                }
                for i, s in enumerate(self.pres["slides"])
            ],
        }


def validate_spec(spec):
    config = spec.get("config", {})
    layout_cfg = config.get("layout", {})
    table_cfg = config.get("table", {})
    features = config.get("features", {})

    PAGE_HEIGHT = 5143500
    PAGE_BOTTOM_MARGIN = layout_cfg.get("page_bottom_margin", 450000)
    MAX_CONTENT_BOTTOM = PAGE_HEIGHT - PAGE_BOTTOM_MARGIN
    SUB_BOTTOM = layout_cfg.get("body_start_y", 1080000)
    BODY_W_DEFAULT = layout_cfg.get("content_w", 8200000)
    BODY_TABLE_GAP = layout_cfg.get("body_table_gap", 60000)
    jp_period = features.get("jp_period_to_newline", True)

    warnings = []
    for i, s in enumerate(spec.get("slides", [])):
        if isinstance(s.get("body"), list):
            s["body"] = "\n".join(str(x) for x in s["body"])
            warnings.append(f"Slide {i+1} ({s.get('id','?')}): body was a list, auto-joined to string")
        layout = s.get("layout", "")
        if layout not in ("multi", "one_column", "blank"):
            continue
        slide_label = f"Slide {i+1} ({s.get('id', '?')})"
        next_y = SUB_BOTTOM

        if s.get("body"):
            body_h = estimate_body_h(s["body"], s.get("bodySize", 10), BODY_W_DEFAULT)
            if "bodyH" not in s:
                s["bodyH"] = body_h
            body_y = s.get("bodyY", next_y)
            body_bottom = body_y + s["bodyH"]
            next_y = body_bottom + BODY_TABLE_GAP
            if body_bottom > MAX_CONTENT_BOTTOM:
                overflow_emu = body_bottom - MAX_CONTENT_BOTTOM
                body_fs = s.get("bodySize", 10)
                line_h_est = int(body_fs * 914400 / 72 * 1.5)
                body_lines = len(s["body"].split("\n"))
                overflow_lines = max(1, -(-overflow_emu // max(line_h_est, 1)))
                warnings.append(
                    f"{slide_label}: body exceeds bottom limit. "
                    f"Body: ~{body_lines} lines, overflow: {overflow_emu} EMU (~{overflow_lines} lines over). "
                    f"ACTION: Split this slide into multiple slides or reduce by ~{overflow_lines} lines (do NOT truncate content). "
                    f"Use (1/N), (2/N) suffixes or distinct titles per sub-topic."
                )

        if s.get("type") == "table" and s.get("table"):
            tbl = s["table"]
            if "y" not in tbl:
                tbl["y"] = next_y
            table_y = tbl["y"]
            data = tbl.get("data", [])
            nr = len(data)
            nc = len(data[0]) if data else 1
            rh = tbl.get("rowHeight", table_cfg.get("default_row_height", 330000))
            tbl_fs = tbl.get("fontSize", config.get("sizes", {}).get("table_body", 8))
            col_widths = tbl.get("columnWidths")
            tbl_w = tbl.get("w", table_cfg.get("default_w", 8200000))

            if col_widths:
                if len(col_widths) != nc:
                    warnings.append(f"{slide_label}: columnWidths has {len(col_widths)} values but table has {nc} columns")
                cw_sum = sum(col_widths)
                if cw_sum < tbl_w * 0.5:
                    warnings.append(f"{slide_label}: columnWidths sum ({cw_sum}) is less than 50% of table width ({tbl_w}). Values must be in EMU (e.g., 2000000), not pt")
                for ci_v, val in enumerate(col_widths):
                    if val < 100000:
                        warnings.append(f"{slide_label}: columnWidths[{ci_v}]={val} is too small. Values must be in EMU (e.g., 500000 = ~0.55 inch)")

            table_header_increment = config.get("sizes", {}).get("table_header_increment", 1)
            effective_h = 0
            for ri, row in enumerate(data):
                max_row_lines = 1
                for ci, cell in enumerate(row):
                    cell_text = str(cell) if cell else ""
                    if ri > 0 and jp_period and "。" in cell_text:
                        cell_text = cell_text.replace("。", "\n")
                    cell_lines = cell_text.count("\n") + 1
                    if col_widths and ci < len(col_widths):
                        cw = col_widths[ci]
                    else:
                        cw = tbl_w // nc
                    cell_padding = 80000
                    usable_w = max(cw - cell_padding, 100000)
                    char_w = int(tbl_fs * 914400 / 72 * 0.5)
                    chars_per = max(usable_w // max(char_w, 1), 1)
                    for line in cell_text.split("\n"):
                        line_chars = display_len(line.strip())
                        wrapped = max(1, -(-line_chars // chars_per))
                        if wrapped > 1:
                            cell_lines += wrapped - 1
                    max_row_lines = max(max_row_lines, cell_lines)
                cell_line_h = int(tbl_fs * 914400 / 72 * 1.4)
                if ri == 0:
                    cell_line_h = int((tbl_fs + table_header_increment) * 914400 / 72 * 1.4)
                cell_pad = 80000
                gs_cell_pad = 73000
                row_h = max(rh, max_row_lines * cell_line_h + cell_pad) + gs_cell_pad
                effective_h += row_h

            table_bottom = table_y + effective_h
            if table_bottom > MAX_CONTENT_BOTTOM:
                scale = (MAX_CONTENT_BOTTOM - table_y) / max(effective_h, 1)
                new_rh = max(int(rh * scale), 200000)
                tbl["rowHeight"] = new_rh

                recalc_h = 0
                for ri2, row2 in enumerate(data):
                    max_rl2 = 1
                    for ci2, cell2 in enumerate(row2):
                        ct2 = str(cell2) if cell2 else ""
                        if ri2 > 0 and jp_period and "\u3002" in ct2:
                            ct2 = ct2.replace("\u3002", "\n")
                        cl2 = ct2.count("\n") + 1
                        if col_widths and ci2 < len(col_widths):
                            cw2 = col_widths[ci2]
                        else:
                            cw2 = tbl_w // nc
                        uw2 = max(cw2 - 80000, 100000)
                        cw_ch2 = int(tbl_fs * 914400 / 72 * 0.5)
                        cp2 = max(uw2 // max(cw_ch2, 1), 1)
                        for ln2 in ct2.split("\n"):
                            lc2 = display_len(ln2.strip())
                            wr2 = max(1, -(-lc2 // cp2))
                            if wr2 > 1:
                                cl2 += wr2 - 1
                        max_rl2 = max(max_rl2, cl2)
                    clh2 = int(tbl_fs * 914400 / 72 * 1.4)
                    if ri2 == 0:
                        clh2 = int((tbl_fs + table_header_increment) * 914400 / 72 * 1.4)
                    rh2 = max(new_rh, max_rl2 * clh2 + 80000) + 73000
                    recalc_h += rh2

                recalc_bottom = table_y + recalc_h
                if recalc_bottom > MAX_CONTENT_BOTTOM:
                    warnings.append(
                        f"{slide_label}: table still overflows after rowHeight shrink ({nr} rows, bottom={recalc_bottom}). "
                        f"ACTION: Split into multiple table slides (do NOT truncate rows)."
                    )
                else:
                    warnings.append(
                        f"{slide_label}: table exceeds bottom → rowHeight auto-shrunk {rh}→{new_rh}. "
                        f"If table has many rows, consider splitting into multiple table slides rather than excessive shrinking."
                    )

        if s.get("type") == "code" and s.get("code"):
            code_spec = s["code"]
            code_fs = code_spec.get("fontSize", config.get("sizes", {}).get("code", 8))
            source_lines = code_spec["source"].count("\n") + 1
            code_pad = config.get("code_block", {}).get("padding", 80000)
            line_h = int(code_fs * 914400 / 72 * 1.4)
            code_h = code_spec.get("h", source_lines * line_h + code_pad * 2)
            code_bottom = next_y + code_h
            code_limit = PAGE_HEIGHT - 150000
            if code_bottom > code_limit:
                max_lines = config.get("code_block", {}).get("max_lines", 25)
                warnings.append(
                    f"{slide_label}: code exceeds bottom limit (bottom={code_bottom}, limit={code_limit}). "
                    f"ACTION: Extract key portions to fit ~{max_lines} lines (code truncation is acceptable per SKILL.md rules)."
                )

    return warnings


def process_spec(svc, drive_svc, pid, spec, keep_existing=False, creds=None):
    config = spec.get("config", {})
    b = SlideBuilder(svc, drive_svc, pid, config)
    b._creds = creds

    print("Step 0: Backup...")
    bk_name, bk_id = b.backup()
    print(f"  Backup created: {bk_name} (id: {bk_id})")

    if keep_existing:
        print("Step 1: Keeping existing slides (prepend mode)...")
        print("  Existing slides will be kept. New slides inserted at the beginning.")
    else:
        print("Step 1: Deleting existing slides...")
        n = b.delete_all_slides()
        print(f"  Deleted {n} slides")

    print("Step 2: Creating slides...")
    slides = spec["slides"]
    b.create_slides(slides)
    print(f"  Created {len(slides)} slides")

    print("Step 3: Filling content...")
    ph_map = b.get_phs()
    agenda_items_fallback = spec.get("agenda_items", [])
    for s in slides:
        if s.get("layout") == "agenda" and not s.get("items") and agenda_items_fallback:
            s["items"] = agenda_items_fallback
    fill_slides(b, slides, ph_map)
    b.flush()
    print("  Content filled.")

    print("Step 4: Hiding empty placeholders...")
    hidden = b.hide_empty_placeholders()
    print(f"  Hidden {hidden} empty placeholders")

    print("Step 5: Verifying...")
    result = b.verify()
    print(f"  Slides: {result['slideCount']}, Issues: {len(result['issues'])}")
    for iss in result["issues"]:
        print(f"    - {iss}")
    for s in result["slides"]:
        print(f"  {s['index']:2d}. [{s['layout']}] {s['objectId']}")

    diagram_count = sum(1 for s in slides if s.get("type") == "diagram")
    if diagram_count:
        print(f"\n  ⚠️  VISUAL CHECK REQUIRED: {diagram_count} diagram slide(s) need thumbnail verification (Step 7b).")

    return result


def fill_slides(b, slides, ph_map):
    config = b.config
    sizes = config.get("sizes", {})
    colors = config.get("colors", {})
    layout_cfg = config.get("layout", {})
    features = config.get("features", {})
    font = config.get("fonts", {}).get("primary", "Arial")

    dark_text_color = {"red": 0, "green": 0, "blue": 0}
    content_x = layout_cfg.get("content_x", 450000)
    content_w = layout_cfg.get("content_w", 8200000)
    body_start_y = layout_cfg.get("body_start_y", 1080000)
    body_table_gap = layout_cfg.get("body_table_gap", 60000)

    for s in slides:
        sid = s["id"]
        layout = s.get("layout", "")
        stype = s.get("type", "bullets")

        if layout == "cover":
            if not features.get("cover_slide", True):
                continue
            b.text(b.get_ph(ph_map, sid, "TITLE", 0), s.get("title", ""), s.get("titleSize", sizes.get("cover_title", 44)), True)
            cover_title_ph = b.get_ph(ph_map, sid, "TITLE", 0)
            if cover_title_ph:
                b._r(
                    {
                        "updatePageElementTransform": {
                            "objectId": cover_title_ph,
                            "applyMode": "ABSOLUTE",
                            "transform": {
                                "scaleX": 2.8667,
                                "scaleY": 0.6401,
                                "translateX": 366600,
                                "translateY": 1188725,
                                "unit": "EMU",
                            },
                        }
                    }
                )
                b._r(
                    {
                        "updateShapeProperties": {
                            "objectId": cover_title_ph,
                            "shapeProperties": {
                                "contentAlignment": "BOTTOM",
                            },
                            "fields": "contentAlignment",
                        }
                    }
                )
                b._r(
                    {
                        "updateTextStyle": {
                            "objectId": cover_title_ph,
                            "style": {
                                "foregroundColor": {
                                    "opaqueColor": {
                                        "rgbColor": {"red": 1, "green": 1, "blue": 1}
                                    }
                                }
                            },
                            "textRange": {"type": "ALL"},
                            "fields": "foregroundColor",
                        }
                    }
                )
            cover_sub_ph = b.get_ph(ph_map, sid, "TITLE", 1)
            if cover_sub_ph and s.get("subtitle"):
                b.text(cover_sub_ph, s["subtitle"], sizes.get("cover_subtitle", 20), True)
                b._r(
                    {
                        "updatePageElementTransform": {
                            "objectId": cover_sub_ph,
                            "applyMode": "ABSOLUTE",
                            "transform": {
                                "scaleX": 2.8667,
                                "scaleY": 0.1475,
                                "translateX": 366600,
                                "translateY": 3160450,
                                "unit": "EMU",
                            },
                        }
                    }
                )
            if s.get("date") and features.get("cover_date", True):
                cover_date_ph = b.get_ph(ph_map, sid, "TITLE", 2)
                if cover_date_ph:
                    b.text(cover_date_ph, s["date"], sizes.get("cover_date", 14))
                    b._r(
                        {
                            "updatePageElementTransform": {
                                "objectId": cover_date_ph,
                                "applyMode": "ABSOLUTE",
                                "transform": {
                                    "scaleX": 2.8667,
                                    "scaleY": 0.0914,
                                    "translateX": 366600,
                                    "translateY": 4359692,
                                    "unit": "EMU",
                                },
                            }
                        }
                    )

        elif layout == "agenda":
            if not features.get("agenda_slide", True):
                continue
            b.text(b.get_ph(ph_map, sid, "BODY", 0), s.get("title", "Agenda"), sizes.get("agenda_title", 28), True)
            items = s.get("items", [])
            body_ph = b.get_ph(ph_map, sid, "BODY", 1)
            n_items = len(items)
            agenda_fs = sizes.get("agenda_items", 16)
            if n_items > 15:
                agenda_fs = min(agenda_fs, 12)
            elif n_items > 10:
                agenda_fs = min(agenda_fs, 14)
            b.text(body_ph, "\n".join(items), agenda_fs)
            if body_ph and items:
                b._r({
                    "createParagraphBullets": {
                        "objectId": body_ph,
                        "textRange": {"type": "ALL"},
                        "bulletPreset": "NUMBERED_DIGIT_ALPHA_ROMAN",
                    }
                })

        elif layout == "divider":
            if not features.get("section_dividers", True):
                continue
            b.text(b.get_ph(ph_map, sid, "BODY", 0), s.get("title", ""), sizes.get("divider", 36), True)

        elif layout == "thanks":
            if not features.get("thanks_slide", True):
                continue
            thanks_ph = b.get_ph(ph_map, sid, "BODY", 0)
            if thanks_ph:
                b._r({"insertText": {"objectId": thanks_ph, "text": "THANK\nYOU"}})
                b._r(
                    {
                        "updateTextStyle": {
                            "objectId": thanks_ph,
                            "style": {
                                "fontFamily": font,
                                "fontSize": {"magnitude": 70, "unit": "PT"},
                                "bold": True,
                                "foregroundColor": {
                                    "opaqueColor": {
                                        "rgbColor": {"red": 1, "green": 1, "blue": 1}
                                    }
                                },
                            },
                            "textRange": {"type": "ALL"},
                            "fields": "fontFamily,fontSize,bold,foregroundColor",
                        }
                    }
                )
                b._r(
                    {
                        "updateTextStyle": {
                            "objectId": thanks_ph,
                            "style": {
                                "foregroundColor": {
                                    "opaqueColor": {
                                        "rgbColor": {"red": 0, "green": 0, "blue": 0}
                                    }
                                },
                            },
                            "textRange": {
                                "type": "FIXED_RANGE",
                                "startIndex": 6,
                                "endIndex": 9,
                            },
                            "fields": "foregroundColor",
                        }
                    }
                )

        elif layout in ("multi", "one_column", "blank"):
            title_ph = b.get_ph(ph_map, sid, "TITLE", 0)
            sub_ph = b.get_ph(ph_map, sid, "SUBTITLE", 0)

            if title_ph:
                b.text(title_ph, s.get("title", ""), s.get("titleSize", sizes.get("title", 24)), True)
            elif layout == "blank" and s.get("title"):
                b.textbox(sid, f"{sid}_t", s["title"], content_x, 200000, content_w, 450000, sizes.get("title_min", 20), True, dark_text_color)

            if sub_ph and s.get("subtitle"):
                b.text(sub_ph, s["subtitle"], s.get("subtitleSize", sizes.get("subtitle", 14)), True)

            next_y = body_start_y

            if s.get("body"):
                body_y = s.get("bodyY", next_y)
                body_fs = s.get("bodySize", sizes.get("body", 10))
                estimated_h = estimate_body_h(s["body"], body_fs, content_w)
                body_h = s.get("bodyH", estimated_h)
                b.body_textbox(sid, f"{sid}_body", s["body"], x=content_x, y=body_y, w=content_w, h=body_h, fs=body_fs)
                next_y = body_y + body_h + body_table_gap

            if stype == "table" and s.get("table"):
                tbl = s["table"]
                table_cfg = config.get("table", {})
                table_y = tbl.get("y", next_y)
                b.table(
                    sid,
                    f"{sid}_tbl",
                    tbl["data"],
                    x=tbl.get("x", table_cfg.get("default_x", content_x)),
                    y=table_y,
                    w=tbl.get("w", table_cfg.get("default_w", content_w)),
                    rh=tbl.get("rowHeight", table_cfg.get("default_row_height", 330000)),
                    fs=tbl.get("fontSize", sizes.get("table_body", 8)),
                    column_widths=tbl.get("columnWidths"),
                )

            elif stype == "code" and s.get("code"):
                code_spec = s["code"]
                b.code(
                    sid,
                    f"{sid}_code",
                    code_spec["source"],
                    language=code_spec.get("language", "sql"),
                    x=code_spec.get("x", content_x),
                    y=next_y,
                    w=code_spec.get("w", content_w),
                    h=code_spec.get("h"),
                    fs=code_spec.get("fontSize", sizes.get("code", 8)),
                )

            elif stype == "diagram" and s.get("diagram"):
                if not features.get("diagram_slide", True):
                    continue
                diagram_cfg = config.get("diagram", {})
                if not diagram_cfg.get("apps_script_url"):
                    import yaml as _yaml
                    _cfg_path = Path(__file__).parent.parent / "config" / "snowflake-gslides-config.yaml"
                    if _cfg_path.exists():
                        with open(_cfg_path) as _cf:
                            diagram_cfg = _yaml.safe_load(_cf).get("diagram", {})
                creds = getattr(b, '_creds', None)
                diagram_y = next_y + 60000
                build_diagram(b, sid, s["diagram"], diagram_y, diagram_cfg, creds)
                b.flush()


def append_spec(svc, drive_svc, pid, spec, insert_after=None, creds=None):
    config = spec.get("config", {})
    b = SlideBuilder(svc, drive_svc, pid, config)
    b._creds = creds
    b.refresh()
    existing_count = len(b.pres.get("slides", []))

    if insert_after is None:
        insert_idx = existing_count
    else:
        insert_idx = min(insert_after, existing_count)

    print(f"Append mode: inserting {len(spec['slides'])} slide(s) at position {insert_idx + 1} (after slide {insert_idx})")
    print(f"  Existing slides: {existing_count}")

    slides = spec["slides"]
    has_divider = any(s.get("layout") == "divider" for s in slides)
    has_multi = any(s.get("layout") in ("multi", "one_column", "blank") for s in slides)
    if has_multi and not has_divider:
        print("  WARNING: Content slides found but no divider included. For new sections, include a divider at the beginning.")

    lmap = {}
    for l in b.pres.get("layouts", []):
        dn = l.get("layoutProperties", {}).get("displayName", "").lower()
        lmap[l["objectId"]] = dn
    has_agenda = any(
        "agenda" in lmap.get(s.get("slideProperties", {}).get("layoutObjectId", ""), "")
        for s in b.pres.get("slides", [])
    )
    if has_agenda and not spec.get("agenda_items"):
        print("  WARNING: Existing slides contain an Agenda but agenda_items not specified in spec.json. Agenda will not be updated.")

    reqs = []
    for i, s in enumerate(slides):
        reqs.append(
            {
                "createSlide": {
                    "objectId": s["id"],
                    "insertionIndex": insert_idx + i,
                    "slideLayoutReference": {"layoutId": s["layoutId"]},
                }
            }
        )
    batch(svc, pid, reqs)
    print(f"  Created {len(slides)} slide(s)")

    ph_map = b.get_phs()
    agenda_items_fallback = spec.get("agenda_items", [])
    for s in slides:
        if s.get("layout") == "agenda" and not s.get("items") and agenda_items_fallback:
            s["items"] = agenda_items_fallback
    fill_slides(b, slides, ph_map)
    b.flush()
    print("  Content filled.")

    if spec.get("agenda_items"):
        print("  Updating Agenda slide...")
        update_agenda(b, spec["agenda_items"])

    added_ids = {s["id"] for s in slides}
    b.refresh()
    reqs = []
    count = 0
    for slide in b.pres["slides"]:
        if slide["objectId"] not in added_ids:
            continue
        for el in slide.get("pageElements", []):
            ph = el.get("shape", {}).get("placeholder")
            if not ph:
                continue
            ph_type = ph.get("type", "")
            if ph_type == "SLIDE_NUMBER":
                continue
            t = ""
            for te in el.get("shape", {}).get("text", {}).get("textElements", []):
                if "textRun" in te:
                    t += te["textRun"]["content"]
            if not t.strip():
                reqs.append(
                    {
                        "updatePageElementTransform": {
                            "objectId": el["objectId"],
                            "applyMode": "ABSOLUTE",
                            "transform": {
                                "scaleX": 0.01,
                                "scaleY": 0.01,
                                "translateX": 20000000,
                                "translateY": 20000000,
                                "unit": "EMU",
                            },
                        }
                    }
                )
                count += 1
    if reqs:
        batch(svc, pid, reqs, 50)
    print(f"  Hidden {count} empty placeholders (appended slides only)")

    result = b.verify()
    print(f"  Total slides: {result['slideCount']}, Issues: {len(result['issues'])}")
    for s in result["slides"]:
        marker = " <-- NEW" if s["objectId"] in added_ids else ""
        print(f"  {s['index']:2d}. [{s['layout']}] {s['objectId']}{marker}")

    diagram_count = sum(1 for s in slides if s.get("type") == "diagram")
    if diagram_count:
        print(f"\n  ⚠️  VISUAL CHECK REQUIRED: {diagram_count} diagram slide(s) need thumbnail verification (Step 7b).")

    return result


def update_agenda(b, agenda_items):
    config = b.config
    font = config.get("fonts", {}).get("primary", "Arial")
    agenda_fs = config.get("sizes", {}).get("agenda_items", 16)

    b.refresh()
    lmap = {}
    for l in b.pres.get("layouts", []):
        dn = l.get("layoutProperties", {}).get("displayName", "")
        lmap[l["objectId"]] = dn

    agenda_slide = None
    for slide in b.pres.get("slides", []):
        lid = slide.get("slideProperties", {}).get("layoutObjectId", "")
        if "agenda" in lmap.get(lid, "").lower():
            agenda_slide = slide
            break

    if not agenda_slide:
        print("  No Agenda slide found. Skipping agenda update.")
        return

    body_phs = []
    for el in agenda_slide.get("pageElements", []):
        ph = el.get("shape", {}).get("placeholder")
        if ph and ph.get("type") == "BODY":
            body_phs.append(el["objectId"])

    if len(body_phs) < 2:
        print("  Agenda slide has fewer than 2 BODY placeholders. Skipping.")
        return

    body1_id = body_phs[1]

    b._r({"deleteText": {"objectId": body1_id, "textRange": {"type": "ALL"}}})
    new_text = "\n".join(agenda_items)
    b._r({"insertText": {"objectId": body1_id, "text": new_text}})
    b._r({
        "updateTextStyle": {
            "objectId": body1_id,
            "style": {
                "fontFamily": font,
                "fontSize": {"magnitude": agenda_fs, "unit": "PT"},
            },
            "textRange": {"type": "ALL"},
            "fields": "fontFamily,fontSize",
        }
    })
    b._r({
        "createParagraphBullets": {
            "objectId": body1_id,
            "textRange": {"type": "ALL"},
            "bulletPreset": "NUMBERED_DIGIT_ALPHA_ROMAN",
        }
    })
    b.flush()
    print(f"  Agenda updated with {len(agenda_items)} items.")


def main():
    parser = argparse.ArgumentParser(description="Build Google Slides from JSON spec")
    parser.add_argument("presentation_id", help="Google Slides presentation ID")
    parser.add_argument("spec", help="JSON specification file")
    parser.add_argument("--output", "-o", help="Output verification JSON")
    parser.add_argument("--keep-existing", action="store_true",
        help="Keep existing slides and prepend new slides at the beginning (creates backup first)")
    parser.add_argument("--append", action="store_true",
        help="Append slides without deleting existing ones")
    parser.add_argument("--insert-after", type=int, default=None,
        help="Insert after this slide number (1-indexed). Default: end")
    args = parser.parse_args()

    with open(args.spec) as f:
        try:
            spec = json.load(f)
        except json.JSONDecodeError as e:
            print(f"ERROR: Failed to parse spec JSON: {e}")
            if "control character" in str(e).lower() or "Invalid" in str(e):
                print("  HINT: Does the body field contain literal newlines?")
                print("        Use \\n (escaped) for newlines in JSON strings.")
            sys.exit(3)

    print("Pre-validation...")
    from lint_spec import lint
    lint_errors, lint_warnings = lint(spec)
    crossing_errors = [e for e in lint_errors if e.startswith("[CROSSING]")]
    blocking_errors = [e for e in lint_errors if not e.startswith("[CROSSING]")]
    if blocking_errors:
        print(f"LINT ERRORS ({len(blocking_errors)}):")
        for e in blocking_errors:
            print(f"  ERROR: {e}")
        print("Fix lint errors before building.")
        sys.exit(5)
    if crossing_errors:
        print(f"LINT CROSSING WARNINGS ({len(crossing_errors)}) — build will proceed, verify with thumbnails:")
        for e in crossing_errors:
            print(f"  CROSSING: {e}")
    if lint_warnings:
        for w in lint_warnings:
            print(f"  LINT WARNING: {w}")

    vw = validate_spec(spec)
    if vw:
        errors = [w for w in vw if "auto-shrunk" not in w]
        for w in vw:
            print(f"  WARNING: {w}")
        if errors:
            print(f"  {len(errors)} unrecoverable layout issue(s). Split overflowing slides (do NOT truncate/drop content).")
            sys.exit(4)
        print(f"  {len(vw)} issue(s) auto-corrected. Continuing...")
    else:
        print("  OK")

    svc, drive_svc, creds = get_services_with_creds()

    if args.append:
        insert_after = args.insert_after if args.insert_after is not None else None
        result = append_spec(svc, drive_svc, args.presentation_id, spec, insert_after, creds=creds)
    else:
        result = process_spec(svc, drive_svc, args.presentation_id, spec,
                              keep_existing=args.keep_existing, creds=creds)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

    if result["issues"]:
        print(f"\nWARNING: {len(result['issues'])} issues found")
        sys.exit(1)
    else:
        print("\nDONE - No issues!")


if __name__ == "__main__":
    main()
