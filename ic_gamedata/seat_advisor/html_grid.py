"""HTML formation grid for Party Advisor."""

from __future__ import annotations

import html
import json

from ic_gamedata.seat_advisor.models import SeatRole, VisualSeatNode, STANDARD_SEAT_ROLES
from ic_gamedata.seat_advisor.role_inference import role_label


_ZONE_COLORS = {
    "front": "#fee2e2",
    "mid": "#fef3c7",
    "back": "#dbeafe",
}


def generate_formation_html(nodes: tuple[VisualSeatNode, ...], *, formation_name: str) -> str:
    if not nodes:
        return _empty_html(formation_name)

    min_x = min(n.x for n in nodes)
    max_x = max(n.x for n in nodes)
    min_y = min(n.y for n in nodes)
    max_y = max(n.y for n in nodes)
    pad = 20.0
    width = max(320, int(max_x - min_x + 120))
    height = max(220, int(max_y - min_y + 120))

    node_payload = []
    for node in nodes:
        if node.hero_id is None:
            continue
        left = (node.x - min_x) + pad
        top = (node.y - min_y) + pad
        bg = _ZONE_COLORS.get(node.zone, "#f3f4f6")
        border = "#dc2626" if node.has_issue else ("#1f6feb" if node.is_bud else "#94a3b8")
        role = node.effective_role or node.inferred_role or "flex"
        node_payload.append(
            {
                "seat": node.seat,
                "heroId": node.hero_id,
                "left": round(left, 1),
                "top": round(top, 1),
                "bg": bg,
                "border": border,
                "name": node.hero_name or f"Champion {node.hero_id}",
                "role": role,
                "roleLabel": role_label(role),  # type: ignore[arg-type]
                "zone": node.zone,
                "inferred": node.inferred_role,
                "chosen": node.chosen_role,
                "isBud": node.is_bud,
            }
        )

    roles_json = json.dumps(list(STANDARD_SEAT_ROLES))
    nodes_json = json.dumps(node_payload, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="nl">
<head>
<meta charset="utf-8"/>
<style>
  body {{ font-family: Segoe UI, sans-serif; margin: 0; padding: 12px; background: #f8fafc; color: #1f2933; }}
  h3 {{ margin: 0 0 8px; font-size: 14px; }}
  .hint {{ color: #6b7280; font-size: 12px; margin-bottom: 10px; }}
  .board {{ position: relative; width: {width}px; height: {height}px; margin: 0 auto; background: #fff;
            border: 1px solid #d8dee6; border-radius: 8px; }}
  .seat {{ position: absolute; width: 92px; min-height: 58px; padding: 6px 8px; border-radius: 8px;
           border: 2px solid; box-sizing: border-box; cursor: pointer; font-size: 11px; }}
  .seat:hover {{ box-shadow: 0 2px 8px rgba(0,0,0,.12); }}
  .seat .slot {{ font-weight: 700; font-size: 10px; color: #6b7280; }}
  .seat .name {{ font-weight: 600; margin: 2px 0; line-height: 1.2; }}
  .seat .role {{ color: #374151; }}
  .seat.bud .name {{ color: #1f6feb; }}
  #rolePanel {{ display: none; margin-top: 12px; padding: 10px; background: #fff; border: 1px solid #d8dee6;
                border-radius: 8px; max-width: {width}px; margin-left: auto; margin-right: auto; }}
  #rolePanel.open {{ display: block; }}
  select, button {{ font: inherit; margin-top: 6px; }}
  button {{ background: #1f6feb; color: #fff; border: 0; padding: 6px 12px; border-radius: 6px; cursor: pointer; }}
</style>
</head>
<body>
<h3>{html.escape(formation_name)}</h3>
<p class="hint">Klik op een champion om de rol te wijzigen. Enemies → rechts (front = naar rechts).</p>
<div class="board" id="board"></div>
<div id="rolePanel">
  <div id="panelTitle"></div>
  <label>Rol: <select id="roleSelect"></select></label><br/>
  <button id="saveRole">Opslaan</button>
  <button id="clearRole" style="background:#6b7280;margin-left:6px;">Reset naar voorstel</button>
</div>
<script>
const ROLES = {roles_json};
const NODES = {nodes_json};
let active = null;
const board = document.getElementById('board');
const panel = document.getElementById('rolePanel');
const panelTitle = document.getElementById('panelTitle');
const roleSelect = document.getElementById('roleSelect');
function render() {{
  board.innerHTML = '';
  for (const n of NODES) {{
    const el = document.createElement('div');
    el.className = 'seat' + (n.isBud ? ' bud' : '');
    el.style.left = n.left + 'px';
    el.style.top = n.top + 'px';
    el.style.background = n.bg;
    el.style.borderColor = n.border;
    el.dataset.seat = n.seat;
    el.dataset.heroId = n.heroId;
    el.innerHTML = '<div class="slot">Slot ' + n.seat + ' · ' + n.zone + '</div>'
      + '<div class="name">' + n.name + '</div>'
      + '<div class="role">' + n.roleLabel + '</div>';
    el.onclick = () => openPanel(n);
    board.appendChild(el);
  }}
}}
function openPanel(n) {{
  active = n;
  panel.classList.add('open');
  let extra = '';
  if (n.chosen && n.inferred && n.chosen !== n.inferred) {{
    extra = ' · voorgesteld: ' + n.inferred;
  }}
  panelTitle.textContent = n.name + ' (slot ' + n.seat + ')' + extra;
  roleSelect.innerHTML = '';
  for (const r of ROLES) {{
    const opt = document.createElement('option');
    opt.value = r;
    opt.textContent = r;
    if (r === n.role) opt.selected = true;
    roleSelect.appendChild(opt);
  }}
  if (window.external && window.external.onSeatSelected) {{
    window.external.onSeatSelected(n.seat, n.heroId);
  }}
  window.location.hash = 'seat-' + n.seat + '-hero-' + n.heroId;
}}
document.getElementById('saveRole').onclick = () => {{
  if (!active) return;
  const role = roleSelect.value;
  window.location.hash = 'setrole-' + active.heroId + '-' + role;
  active.role = role;
  render();
}};
document.getElementById('clearRole').onclick = () => {{
  if (!active) return;
  window.location.hash = 'clearrole-' + active.heroId;
  active.role = active.inferred || 'flex';
  active.chosen = null;
  render();
}};
render();
</script>
</body>
</html>"""


def _empty_html(formation_name: str) -> str:
    return f"""<!DOCTYPE html><html><body style="font-family:Segoe UI;padding:12px;">
    <h3>{html.escape(formation_name)}</h3><p>Geen formatie-posities beschikbaar.</p></body></html>"""
