"""tax-collect サイト追加用 操作記録ツール

使い方:
    python skills/tax-collect/recorder.py --code newsite --start-url https://example.com/

動作:
    1. Playwright persistent context（既存プロファイル使用）でブラウザ起動
    2. tracing / HAR / イベントフックを開始
    3. ユーザーがブラウザで対象サイトを操作・PDF DL まで実施
    4. ターミナルで Enter キー（任意ラベル可）で「マイルストーン」記録 + DOM dump
    5. 'q' + Enter で停止 → output/recorder/<code>/<timestamp>/ に成果物保存

成果物:
    trace.zip       Playwright Trace Viewer で操作再現（スクショ+DOM+ソース）
    network.har     全ネットワーク（リクエスト・レスポンス・ヘッダ・cookie）
    events.jsonl    framenavigated / popup / download / dialog / console
                    + user_click / user_input / user_change / user_submit の時系列
                    （ユーザー操作は context.add_init_script + expose_binding で
                     全 page に DOM event listener を inject して捕捉、password はマスク）
    dom_*.html      マイルストーン地点と最終地点の DOM スナップショット
    milestones.txt  ユーザーが Enter で記録したラベル一覧
    summary.md      URL 推移・popup・download・ユーザー操作の要約（実装の起点）

注意:
    既存の persistent context（~/.money-ops-browser/<code>/）を流用するため、
    過去にログイン済みなら cookie/storage が引き継がれる。新規プロファイル使用時は
    --fresh で別ディレクトリを使う。
"""

from __future__ import annotations

import argparse
import json
import threading
from datetime import datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _now() -> str:
    return datetime.now().isoformat()


def _write_summary(out_dir: Path, events: list[dict], milestones: list[dict]) -> None:
    nav = [e for e in events if e["kind"] == "framenavigated"]
    popups = [e for e in events if e["kind"] == "popup"]
    downloads = [e for e in events if e["kind"] == "download"]
    dialogs = [e for e in events if e["kind"] == "dialog"]
    user_ops = [e for e in events if e["kind"].startswith("user_")]

    lines: list[str] = []
    lines.append(f"# recorder summary\n")
    lines.append(f"- generated: {_now()}\n")
    lines.append(f"- events: {len(events)} / nav: {len(nav)} / popup: {len(popups)} / download: {len(downloads)} / dialog: {len(dialogs)} / user_ops: {len(user_ops)}\n")

    lines.append("\n## milestones\n")
    if milestones:
        for i, m in enumerate(milestones, 1):
            lines.append(f"{i}. `{m['ts']}` — {m['label']}\n")
    else:
        lines.append("(なし)\n")

    lines.append("\n## URL 遷移（main frame）\n")
    seen_url: set[str] = set()
    for e in nav:
        u = e.get("url", "")
        if u in seen_url:
            continue
        seen_url.add(u)
        lines.append(f"- `{e['ts']}` {u}\n")

    lines.append("\n## popup\n")
    for e in popups:
        lines.append(f"- `{e['ts']}` {e.get('url', '')}\n")
    if not popups:
        lines.append("(なし)\n")

    lines.append("\n## download\n")
    for e in downloads:
        lines.append(f"- `{e['ts']}` suggested=`{e.get('suggested', '')}` url={e.get('url', '')}\n")
    if not downloads:
        lines.append("(なし)\n")

    lines.append("\n## dialog\n")
    for e in dialogs:
        lines.append(f"- `{e['ts']}` type={e.get('type', '')} message={e.get('message', '')[:200]}\n")
    if not dialogs:
        lines.append("(なし)\n")

    lines.append("\n## ユーザー操作（時系列）\n")
    if user_ops:
        for e in user_ops:
            kind = e["kind"]
            ts = e["ts"]
            if kind == "user_click":
                tag = e.get("tag", "")
                text = e.get("text", "")
                name = e.get("name", "") or e.get("href", "")
                sel = e.get("selector", "")
                lines.append(f"- `{ts}` **click** {tag}[{name}] text=\"{text}\" sel=`{sel}`\n")
            elif kind == "user_input":
                name = e.get("name", "")
                typ = e.get("type", "")
                val = e.get("value", "")
                lines.append(f"- `{ts}` **input** {name}({typ})=\"{val}\"\n")
            elif kind == "user_change":
                name = e.get("name", "")
                val = e.get("value", "")
                txt = e.get("selectedText", "")
                lines.append(f"- `{ts}` **change** {name} value=\"{val}\" text=\"{txt}\"\n")
            elif kind == "user_submit":
                name = e.get("name", "")
                action = e.get("action", "")
                lines.append(f"- `{ts}` **submit** {name} action={action}\n")
    else:
        lines.append("(なし)\n")

    (out_dir / "summary.md").write_text("".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="tax-collect サイト追加用 操作記録ツール")
    parser.add_argument("--code", required=True, help="サイトコード（例: newsite）")
    parser.add_argument("--start-url", default=None, help="起動時に開く URL")
    parser.add_argument("--fresh", action="store_true", help="新規プロファイル使用（既存cookie流用しない）")
    args = parser.parse_args()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = _PROJECT_ROOT / "output" / "recorder" / args.code / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[recorder] 出力先: {out_dir}")

    if args.fresh:
        profile_dir = _PROJECT_ROOT / "output" / "recorder" / args.code / f"profile_{ts}"
    else:
        profile_dir = Path.home() / ".money-ops-browser" / args.code
    profile_dir.mkdir(parents=True, exist_ok=True)
    print(f"[recorder] プロファイル: {profile_dir}")

    import queue as _queue

    events: list[dict] = []
    milestones: list[dict] = []
    dom_seq = [0]
    stop_event = threading.Event()
    state: dict = {}
    milestone_queue: _queue.Queue[str] = _queue.Queue()

    def add_event(kind: str, **data) -> None:
        e = {"ts": _now(), "kind": kind, **data}
        events.append(e)
        sig = data.get("url") or data.get("label") or data.get("suggested") or ""
        print(f"[event] {kind}: {sig}")

    def save_dom(page, label: str) -> None:
        dom_seq[0] += 1
        seq = dom_seq[0]
        try:
            html = page.content()
            url = page.url
        except Exception as e:
            print(f"[recorder] DOM 保存失敗 ({label}): {e}")
            return
        path = out_dir / f"dom_{seq:03d}_{label}.html"
        path.write_text(html, encoding="utf-8")
        add_event("dom_dump", file=path.name, url=url, label=label)

    def attach_page_events(page) -> None:
        page.on(
            "framenavigated",
            lambda f: add_event("framenavigated", url=f.url) if f == f.page.main_frame else None,
        )
        def on_popup(p):
            add_event("popup", url=p.url)
            attach_page_events(p)
        page.on("popup", on_popup)
        page.on("download", lambda d: add_event("download", suggested=d.suggested_filename, url=d.url))
        page.on("dialog", lambda d: add_event("dialog", type=d.type, message=d.message))
        page.on("console", lambda m: add_event("console", level=m.type, text=m.text[:300]))

    def on_user_event(source, kind, data) -> None:
        """JS 側 (init_script) からの user_click / user_input / user_change / user_submit を受信。
        events.jsonl に時系列で追記し、実装時の操作復元情報として活用する。"""
        # source.page から URL も付与
        try:
            url = source.page.url
        except Exception:
            url = ""
        add_event(kind, url=url, **(data if isinstance(data, dict) else {"value": data}))

    def input_loop() -> None:
        print("\n[recorder] 操作開始。Enter=milestone（ラベル任意） / 'q'+Enter=停止\n")
        while not stop_event.is_set():
            try:
                line = input()
            except EOFError:
                stop_event.set()
                break
            if line.strip().lower() == "q":
                stop_event.set()
                break
            label = line.strip() or f"milestone_{len(milestones)+1}"
            milestones.append({"ts": _now(), "label": label})
            print(f"[milestone] {label} (DOM保存待機中...)")
            milestone_queue.put(label)

    # 全 page に inject する DOM event listener（user_click/input/change/submit）
    # password はマスク、value は 200 chars truncate
    user_event_js = r"""
    (() => {
      if (window.__recorder_installed) return;
      window.__recorder_installed = true;

      function getCssPath(el) {
        if (!(el instanceof Element)) return '';
        const path = [];
        while (el && el.nodeType === Node.ELEMENT_NODE && path.length < 6) {
          let sel = el.nodeName.toLowerCase();
          if (el.id) { sel += '#' + el.id; path.unshift(sel); break; }
          const cls = (el.className || '').toString().trim().split(/\s+/).slice(0, 2).join('.');
          if (cls) sel += '.' + cls;
          path.unshift(sel);
          el = el.parentElement;
        }
        return path.join(' > ');
      }

      function safeText(s, n) { return (s || '').toString().replace(/\s+/g, ' ').trim().slice(0, n); }

      document.addEventListener('click', (e) => {
        const el = e.target;
        if (!el || !el.tagName) return;
        try {
          window.__recorder_event('user_click', {
            tag: el.tagName,
            text: safeText(el.textContent, 100),
            role: el.getAttribute && el.getAttribute('role'),
            name: el.getAttribute && (el.getAttribute('name') || el.id || el.getAttribute('aria-label')),
            href: el.getAttribute && el.getAttribute('href'),
            selector: getCssPath(el),
          });
        } catch (err) {}
      }, true);

      document.addEventListener('change', (e) => {
        const el = e.target;
        if (!el || !el.tagName) return;
        try {
          if (el.tagName === 'SELECT') {
            const opt = el.options[el.selectedIndex];
            window.__recorder_event('user_change', {
              name: el.name || el.id,
              value: el.value,
              selectedText: opt ? safeText(opt.text, 100) : '',
              selector: getCssPath(el),
            });
          } else if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
            const isPassword = el.type === 'password';
            const data = {
              name: el.name || el.id,
              type: el.type,
              selector: getCssPath(el),
            };
            // type 別の意味ある属性を取得
            if (el.type === 'file') {
              data.files = Array.from(el.files || []).map(f => f.name).slice(0, 5);
            } else if (el.type === 'checkbox' || el.type === 'radio') {
              data.checked = el.checked;
              data.value = safeText(el.value, 100);
            } else {
              data.value = isPassword ? '***MASKED***' : safeText(el.value, 200);
            }
            window.__recorder_event('user_input', data);
          }
        } catch (err) {}
      }, true);

      document.addEventListener('submit', (e) => {
        const f = e.target;
        if (!f || !f.tagName) return;
        try {
          window.__recorder_event('user_submit', {
            name: f.name || f.id,
            action: f.action,
            method: f.method,
          });
        } catch (err) {}
      }, true);
    })();
    """

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            str(profile_dir),
            headless=False,
            record_har_path=str(out_dir / "network.har"),
            args=[
                "--disable-blink-features=AutomationControlled",
                "--use-angle=d3d11",
            ],
            ignore_default_args=["--enable-automation"],
        )
        # 全 page（popup 含む）で user 操作を捕捉
        context.expose_binding("__recorder_event", on_user_event)
        context.add_init_script(user_event_js)
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
        page = context.new_page()
        state["page"] = page
        attach_page_events(page)

        if args.start_url:
            page.goto(args.start_url)

        def on_context_close():
            if not stop_event.is_set():
                print("\n[recorder] ブラウザが閉じられました → 停止")
                stop_event.set()

        context.on("close", lambda: on_context_close())

        thread = threading.Thread(target=input_loop, daemon=True)
        thread.start()

        try:
            while not stop_event.is_set():
                try:
                    label = milestone_queue.get(timeout=0.2)
                except _queue.Empty:
                    # CDP イベントポンプ: 新 popup target の waitForDebugger 解除のため
                    # 短い Playwright API 呼び出しでメッセージキューを drain
                    try:
                        for pg in context.pages:
                            if not pg.is_closed():
                                pg.evaluate("1")
                    except Exception:
                        pass
                    continue
                pages = [pg for pg in context.pages if not pg.is_closed()]
                for i, pg in enumerate(pages):
                    suffix = f"milestone_{label}_p{i}" if len(pages) > 1 else f"milestone_{label}"
                    try:
                        save_dom(pg, suffix)
                    except Exception as e:
                        print(f"[recorder] milestone DOM 保存失敗 ({suffix}): {e}")
        except KeyboardInterrupt:
            print("\n[recorder] Ctrl+C 検出 → 停止")
            stop_event.set()

        print("[recorder] tracing 停止中（trace.zip 生成）...")
        try:
            for i, pg in enumerate([p for p in context.pages if not p.is_closed()]):
                suffix = f"final_p{i}" if len(context.pages) > 1 else "final"
                try:
                    save_dom(pg, suffix)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            context.tracing.stop(path=str(out_dir / "trace.zip"))
            print("[recorder] trace.zip 保存完了")
        except Exception as e:
            print(f"[recorder] tracing 停止失敗（ブラウザ既閉鎖）: {e}")
        try:
            context.close()
        except Exception:
            pass

    (out_dir / "events.jsonl").write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in events) + ("\n" if events else ""),
        encoding="utf-8",
    )
    (out_dir / "milestones.txt").write_text(
        "\n".join(f"{m['ts']}\t{m['label']}" for m in milestones) + ("\n" if milestones else ""),
        encoding="utf-8",
    )
    _write_summary(out_dir, events, milestones)

    print(f"\n[recorder] 完了 → {out_dir}")
    print("  - trace.zip    : npx playwright show-trace で再生")
    print("  - network.har  : HAR Viewer / Chrome DevTools")
    print("  - events.jsonl : ユーザー操作含む全 event 時系列")
    print("  - summary.md   : 実装起点（URL推移・popup・DL・ユーザー操作要約）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
