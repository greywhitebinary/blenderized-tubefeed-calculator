"""One copy-to-clipboard block, shared by EN-Calc and BTF-Calc.

TWIN FILE. This exists twice, as EN-Calc's webapp/copy_block.py and as
BTF-Calc's app/copy_block.py. The two apps are separate repositories with no
shared package, so it is duplicated rather than imported.

The two copies are BYTE-IDENTICAL, deliberately, including this docstring:
that way `diff` between them is the whole sync check, and a difference is
always a bug rather than something to read carefully. Nothing here reaches
into either app's stylesheet, state or naming, so keeping them identical
costs nothing. If you change one, copy the file to the other.

That constrains the formatting. The two repos run black at different line
lengths -- EN-Calc at 88, BTF-Calc at 100 -- so anything black would wrap at
88 and rejoin at 100 breaks the identity the moment each repo formats. Keep
every statement short enough that both configurations leave it alone; where
that gets awkward, use a plain local variable rather than an expression
black has an opinion about. Verify with:

    black --line-length 88 --check copy_block.py
    black --line-length 100 --check copy_block.py

WHY IT EXISTS
-------------
The two calculators presented copyable text in two different ways. EN-Calc
had a "Copy chart note" button of its own; BTF-Calc had no button at all and
relied on Streamlit's hover copy icon on st.code, which is elegant but names
itself to nobody. This is one control, in one place, in both apps.

NO --st-* VARIABLES, DELIBERATELY
---------------------------------
The previous version of this component styled itself with var(--st-font),
var(--st-text-color), var(--st-background-color), var(--st-primary-color) and
var(--st-border-color). None of those resolve. `--st-` appears nowhere in
Streamlit 1.62's shipped frontend -- the tokens exist only in Streamlit's own
Components v2 docstring examples -- so every declaration using one was
invalid and silently dropped. That is most of why the old button looked
unlike anything else in the app: its `background` shorthand was invalid and
fell back to transparent, and its border-color fell back to currentColor,
drawing a hard dark line where a faint one was intended, while `font:
inherit` pulled the label up to the page's 20px base.

So the colours here are written out, and dark mode is handled with a
prefers-color-scheme media query. Do not reintroduce a var() with a fallback
either: it reads as though it adapts, when it never will.

TYPOGRAPHY
----------
Two type systems share this box on purpose.

The note body is Arial at a FIXED 15px. Epic's note editor defaults to Arial
11pt and converts pasted content into it, so ~15px on screen is roughly what
the note will look like once it lands in the chart. It is deliberately not
sized in rem: it previews a foreign surface, so it must not scale with the
app's 125% base the way the chrome around it does.

The toolbar is app chrome, so it is 0.875rem -- 17.5px against that 125%
root, the same size as the .box-heading above it, so heading and button read
as peers on one row. rem resolves against the document root even inside the
shadow root, so this tracks the app.

WHAT GOES ON THE CLIPBOARD
--------------------------
Both text/html and text/plain, because clinicians paste into rich-text note
editors. The HTML flavour is restricted to <div>, <strong> and <br>: Epic
re-fonts everything to Arial 11 and does not care, but Cerner's Dynamic
Documentation inherits pasted markup, and the documented failure there is
source-document styling arriving with the text and fighting the system font.
Keeping font declarations out of the payload is what prevents that.

The editable variant sanitises paste for the same reason. Anything pasted in
is reduced to plain text before it enters the note, so Word markup cannot
ride through the editor and out via the clipboard.
"""

from __future__ import annotations

from hashlib import sha256

import streamlit as st

# Streamlit's own copy glyph: two overlapping rounded rectangles. Inline SVG
# rather than the U+29C9 character, whose coverage across system fonts is
# unreliable and which renders as tofu when it is missing. aria-hidden because
# the visible label is already the button's accessible name -- an aria-label
# here would override it and risk diverging from it (WCAG 2.5.3).
_COPY_ICON = (
    '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" '
    'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
    'stroke-linejoin="round" aria-hidden="true" focusable="false">'
    '<rect x="9" y="9" width="12" height="12" rx="2"></rect>'
    '<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>'
    "</svg>"
)

COPY_BLOCK_HTML = f"""
<div class="copy-toolbar">
  <button data-action="copy" type="button">{_COPY_ICON}<span data-role="label"></span></button>
  <button data-action="refresh" type="button" hidden>Update from calculator</button>
  <span data-role="status" role="alert"></span>
  <span data-role="copy-status" aria-live="polite"></span>
</div>
<div class="copy-body"></div>
"""

# Palette written out rather than read from the theme; see the module
# docstring. These track .streamlit/config.toml by hand in both repos.
COPY_BLOCK_CSS = """
:host { color: inherit; }

.copy-toolbar {
    display: flex;
    gap: .55rem;
    align-items: center;
    flex-wrap: wrap;
    justify-content: flex-end;
    margin-bottom: .5rem;
}

/* 0.875rem matches the .box-heading this sits beside; see the module
   docstring on why the toolbar and the body are sized differently. */
button {
    display: inline-flex;
    align-items: center;
    gap: .4rem;
    padding: .25rem .7rem;
    border: 1px solid color-mix(in srgb, currentColor 18%, transparent);
    border-radius: .3rem;
    background: transparent;
    color: inherit;
    font-family: inherit;
    font-size: .875rem;
    line-height: 1.5;
    cursor: pointer;
}
button:hover { background: rgba(128, 128, 128, 0.15); }
button:focus-visible {
    outline: none;
    border-color: #A4243A;
    box-shadow: 0 0 0 2px rgba(164, 36, 58, 0.25);
}

/* Empty at rest and filled when something happens, so the live regions
   actually announce. Toggling visibility on a region that already holds its
   text is the pattern assistive technology may never notice. */
[data-role="status"] { font-size: .875rem; opacity: .8; }
[data-role="copy-status"] { font-size: .875rem; }
[data-role="status"]:empty, [data-role="copy-status"]:empty { display: none; }

/* Arial 15px previews how the note lands in Epic; deliberately not rem. */
.copy-body {
    border: 1px solid rgba(128, 128, 128, 0.35);
    border-radius: .45rem;
    padding: .9rem 1rem;
    font-family: Arial, Helvetica, sans-serif;
    font-size: 15px;
    line-height: 1.45;
    overflow-wrap: anywhere;
    white-space: pre-wrap;
}
.copy-body[contenteditable="true"] { min-height: 610px; white-space: normal; }
.copy-body:focus {
    outline: none;
    border-color: #A4243A;
    box-shadow: 0 0 0 2px rgba(164, 36, 58, 0.25);
}

@media (prefers-color-scheme: dark) {
    button:focus-visible {
        border-color: #E0708A;
        box-shadow: 0 0 0 2px rgba(224, 112, 138, 0.3);
    }
    .copy-body:focus {
        border-color: #E0708A;
        box-shadow: 0 0 0 2px rgba(224, 112, 138, 0.3);
    }
}
"""

COPY_BLOCK_JS = """
export default function(component) {
  const { data, parentElement } = component;
  const body = parentElement.querySelector('.copy-body');
  const copyBtn = parentElement.querySelector('[data-action="copy"]');
  const refresh = parentElement.querySelector('[data-action="refresh"]');
  const status = parentElement.querySelector('[data-role="status"]');
  const copyStatus = parentElement.querySelector('[data-role="copy-status"]');

  parentElement.querySelector('[data-role="label"]').textContent = data.label;

  if (data.editable) {
    body.setAttribute('contenteditable', 'true');
    body.setAttribute('role', 'textbox');
    body.setAttribute('aria-multiline', 'true');
    body.setAttribute('aria-label', data.label);
  }

  let saved;
  if (data.editable) {
    try { saved = JSON.parse(sessionStorage.getItem(data.storageKey)); } catch (_) { saved = null; }
    if (!saved) {
      saved = {html: data.bodyHtml, generatedHtml: data.bodyHtml, signature: data.signature};
    } else if (saved.signature !== data.signature) {
      if (saved.html === saved.generatedHtml) {
        saved = {html: data.bodyHtml, generatedHtml: data.bodyHtml, signature: data.signature};
      } else {
        refresh.hidden = false;
        // Set the text now rather than revealing text that was already there:
        // an alert region announces when its content changes, not when it
        // becomes visible.
        status.textContent = 'Calculations changed. Updating will replace your edits.';
      }
    }
    body.innerHTML = saved.html;
    sessionStorage.setItem(data.storageKey, JSON.stringify(saved));
    body.oninput = () => {
      saved.html = body.innerHTML;
      sessionStorage.setItem(data.storageKey, JSON.stringify(saved));
      copyStatus.textContent = '';
    };
    // Reduce every paste to plain text, so nothing pasted from Word can enter
    // the note and then reach the clipboard as text/html. Cerner inherits
    // pasted markup, and foreign font declarations are the documented failure.
    body.addEventListener('paste', (event) => {
      event.preventDefault();
      const text = (event.clipboardData || window.clipboardData).getData('text/plain');
      const selection = window.getSelection();
      if (!selection || !selection.rangeCount) return;
      const range = selection.getRangeAt(0);
      range.deleteContents();
      const fragment = document.createDocumentFragment();
      const lines = text.split(/\\r\\n|\\r|\\n/);
      lines.forEach((line, index) => {
        if (index > 0) fragment.appendChild(document.createElement('br'));
        fragment.appendChild(document.createTextNode(line));
      });
      const last = fragment.lastChild;
      range.insertNode(fragment);
      if (last) {
        range.setStartAfter(last);
        range.collapse(true);
        selection.removeAllRanges();
        selection.addRange(range);
      }
      body.dispatchEvent(new Event('input'));
    });
    refresh.onclick = () => {
      saved = {html: data.bodyHtml, generatedHtml: data.bodyHtml, signature: data.signature};
      body.innerHTML = saved.html;
      sessionStorage.setItem(data.storageKey, JSON.stringify(saved));
      refresh.hidden = true;
      status.textContent = '';
    };
  } else {
    body.innerHTML = data.bodyHtml;
  }

  copyBtn.onclick = async () => {
    const plain = body.innerText;
    try {
      if (window.ClipboardItem && navigator.clipboard && navigator.clipboard.write) {
        await navigator.clipboard.write([new ClipboardItem({
          'text/html': new Blob([body.innerHTML], {type: 'text/html'}),
          'text/plain': new Blob([plain], {type: 'text/plain'})
        })]);
      } else if (navigator.clipboard) {
        await navigator.clipboard.writeText(plain);
      } else {
        throw new Error('no clipboard');
      }
      copyStatus.textContent = 'Copied.';
    } catch (_) {
      // navigator.clipboard needs a secure context, so this is the path taken
      // when the app is opened over plain http from another device on the LAN.
      // Select the text so the browser's own Copy still works.
      const range = document.createRange();
      range.selectNodeContents(body);
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
      copyStatus.textContent = 'Select Copy in your browser to finish copying.';
    }
  };
}
"""


def render_copy_block(
    body_html: str,
    *,
    block_id: str,
    label: str = "Copy note",
    editable: bool = False,
    storage_key: str | None = None,
    instance: str | None = None,
) -> None:
    """Render text with one copy button above it.

    `body_html` must already be escaped and may use only <div>, <strong> and
    <br>; see the module docstring on why the payload is kept that narrow.

    `block_id` names the COMPONENT and must be stable for the life of the app
    -- one per place a copy block appears. `instance` varies the widget KEY
    without registering a second component, which is what a caller wants when
    the same block should remount for a new case or record. Folding a changing
    value into block_id instead would add a registry entry every time it
    changed.

    When `editable` is true the block is a contenteditable draft backed by
    sessionStorage under `storage_key`, and it offers to refresh itself when
    the generated text changes underneath a user who has made edits. The
    draft never reaches Python, which is what keeps it out of saved records.
    """
    if editable and not storage_key:
        raise ValueError("an editable copy block needs a storage_key")

    widget_key = f"_copy_block_{block_id}"
    if instance:
        widget_key = f"{widget_key}_{instance}"

    component = st.components.v2.component(
        f"copy_block_{block_id}",
        html=COPY_BLOCK_HTML,
        css=COPY_BLOCK_CSS,
        js=COPY_BLOCK_JS,
    )
    component(
        data={
            "bodyHtml": body_html,
            "label": label,
            "editable": editable,
            "storageKey": storage_key or "",
            "signature": sha256(body_html.encode("utf-8")).hexdigest(),
        },
        key=widget_key,
    )
