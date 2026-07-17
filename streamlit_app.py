"""
streamlit_app.py
================
Streamlit UI for Mail Automation System.
Send personalised emails with optional attachments via Brevo API.
Supports Excel data upload, {{placeholder}} auto-detection, and campaign presets.
"""

import base64
import re
import time
from typing import Optional
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

import campaign_manager

# ── Page config ──

st.set_page_config(
    page_title="Mail Automation System",
    page_icon="📧",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Session state defaults ──

_AUTO_VARS = {"mailing_name", "sender_name", "sender_email"}

_DEFAULTS: dict[str, object] = {
    "api_key": "",
    "sender_email": "",
    "sender_name": "",
    "delay": 30,
    "campaign_name": "",
    "mailing_name": "gradients",
    "subject": "",
    "body": "",
    "results": [],
    "sending": False,
}
for k, v in _DEFAULTS.items():
    st.session_state.setdefault(k, v)


# =============================================================================
# HELPERS
# =============================================================================


def detect_placeholders(text: str) -> set[str]:
    """Return all {{variable}} names found in *text*."""
    return {m.strip() for m in re.findall(r"\{\{([^}]+?)\}\}", text) if m.strip()}


def find_best_match(var: str, columns: list[str]) -> int:
    """Return index of the column that best matches *var* (case-insensitive)."""
    v = var.lower()
    for i, col in enumerate(columns):
        if col.strip().lower() == v:
            return i
    for i, col in enumerate(columns):
        if v in col.strip().lower():
            return i
    return 0


def body_to_html(text: str) -> str:
    """Convert plain text to HTML when no HTML tags are present."""
    if re.search(r"<[a-z][\s\S]*>", text, re.I):
        return text
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    return "\n".join(f"<p>{'<br>'.join(p.split(chr(10)))}</p>" for p in paras)


def send_brevo(
    api_key: str,
    sender: dict,
    to_email: str,
    to_name: str,
    subject: str,
    html_body: str,
    attachment_bytes: Optional[bytes] = None,
    attachment_name: Optional[str] = None,
) -> tuple[bool, Optional[str]]:
    """Send a single email via Brevo REST API.  Returns (success, error_msg)."""
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "api-key": api_key,
    }
    payload: dict = {
        "sender": {"name": sender["name"], "email": sender["email"]},
        "to": [{"email": to_email, "name": to_name or to_email.split("@")[0]}],
        "subject": subject,
        "htmlContent": html_body,
    }
    if attachment_bytes and attachment_name:
        payload["attachment"] = [
            {
                "content": base64.b64encode(attachment_bytes).decode("utf-8"),
                "name": attachment_name,
            }
        ]

    try:
        r = requests.post(url, json=payload, headers=headers, timeout=30)
        if r.status_code == 201:
            return True, None
        return False, f"HTTP {r.status_code}: {r.text[:200]}"
    except requests.RequestException as e:
        return False, str(e)


def find_email_column(df: pd.DataFrame) -> Optional[str]:
    """Return the column name that holds email addresses, or None."""
    for col in df.columns:
        if col.strip().lower() == "email":
            return col
    return None


def find_name_column(df: pd.DataFrame) -> Optional[str]:
    """Return the column name that holds recipient names, or None."""
    targets = ["name", "college name", "candidate name", "recipient name"]
    for col in df.columns:
        if col.strip().lower() in targets:
            return col
    return None


# =============================================================================
# SIDEBAR
# =============================================================================

with st.sidebar:
    st.header("💾 Presets")

    presets = campaign_manager.get_preset_names()
    preset_opts = [""] + presets if presets else [""]
    selected = st.selectbox("Load preset", preset_opts, key="preset_selector")

    if selected:
        data = campaign_manager.load_presets()
        if selected in data:
            p = data[selected]
            for field in (
                "campaign_name",
                "mailing_name",
                "subject",
                "body",
                "sender_email",
                "sender_name",
                "delay",
            ):
                if field in p:
                    st.session_state[field] = p[field]
            st.session_state._preset_loaded = True

    if st.session_state.pop("_preset_loaded", False):
        st.success(f"Loaded: {selected}")

    save_name = st.text_input("Save as...", key="save_preset_name")
    if st.button("Save Preset") and save_name.strip():
        campaign_manager.save_preset(
            save_name.strip(),
            {
                "campaign_name": st.session_state.campaign_name,
                "mailing_name": st.session_state.mailing_name,
                "subject": st.session_state.subject,
                "body": st.session_state.body,
                "sender_email": st.session_state.sender_email,
                "sender_name": st.session_state.sender_name,
                "delay": st.session_state.delay,
            },
        )
        st.success(f"Saved: {save_name.strip()}")
        st.rerun()

    if selected and st.button("Delete Selected Preset"):
        campaign_manager.delete_preset(selected)
        st.success(f"Deleted: {selected}")
        st.rerun()

    st.divider()
    st.header("🔐 Credentials")
    st.text_input("Brevo API Key", type="password", key="api_key")
    st.text_input("Sender Email", key="sender_email")
    st.text_input("Sender Name", key="sender_name")

    st.divider()
    st.header("⚙️ Settings")
    st.number_input(
        "Delay between emails (seconds)",
        min_value=1,
        max_value=300,
        value=30,
        key="delay",
    )


# =============================================================================
# MAIN PANEL
# =============================================================================

st.title("📧 Mail Automation System")

# ── 1. Campaign Setup ──

with st.expander("📝 1. Campaign Setup", expanded=True):
    col1, col2 = st.columns(2)
    with col1:
        st.text_input("Campaign Name (for reference)", key="campaign_name")
    with col2:
        st.text_input(
            "Mailing Name",
            key="mailing_name",
            help="e.g. 'gradients', 'team gradients'.  "
            "Use as {{mailing_name}} in your template.",
        )

    st.text_input(
        "Email Subject",
        key="subject",
        help="Use {{placeholders}} like {{name}}, {{role}}, etc.",
    )
    st.text_area(
        "Email Body",
        key="body",
        height=350,
        help="Use {{placeholders}} like {{name}}, {{mailing_name}}, etc.  "
        "HTML tags are supported; plain text is auto-converted.",
    )

    # Detect placeholders
    all_text = st.session_state.subject + " " + st.session_state.body
    placeholder_vars = sorted(detect_placeholders(all_text))
    st.session_state.placeholder_vars = placeholder_vars

    if placeholder_vars:
        auto = [v for v in placeholder_vars if v in _AUTO_VARS]
        mappable = [v for v in placeholder_vars if v not in _AUTO_VARS]
        parts = []
        if auto:
            parts.append(
                "🔹 **Auto-filled:** " + ", ".join(f"`{{{{{v}}}}}`" for v in auto)
            )
        if mappable:
            parts.append(
                "🔸 **Needs mapping:** " + ", ".join(f"`{{{{{v}}}}}`" for v in mappable)
            )
        st.markdown("  \n".join(parts))
    else:
        st.info("Add `{{placeholders}}` to your subject or body.")

# ── 2. Data Upload ──

with st.expander("📊 2. Data Upload", expanded=True):
    uploaded = st.file_uploader(
        "Upload Excel file (.xlsx / .xls)",
        type=["xlsx", "xls"],
        key="excel_upload",
    )
    if uploaded:
        df = pd.read_excel(uploaded, dtype=str).fillna("")
        st.session_state.df = df
        st.success(f"Loaded **{len(df)}** rows from `{uploaded.name}`")
        st.dataframe(df.head(20), use_container_width=True)
    else:
        st.session_state.df = None
        st.info(
            "Upload an Excel file with recipient data.  "
            "The file must contain an **Email** column."
        )

# ── 3. Variable Mapping ──

df = st.session_state.get("df")
placeholder_vars = st.session_state.get("placeholder_vars", [])
mappable_vars = [v for v in placeholder_vars if v not in _AUTO_VARS]

if df is not None and mappable_vars:
    with st.expander("🔗 3. Variable Mapping", expanded=True):
        st.markdown("Map each `{{placeholder}}` to an Excel column:")
        cols = list(df.columns)
        for var in mappable_vars:
            default_idx = find_best_match(var, cols)
            st.selectbox(
                f"`{{{{{var}}}}}`",
                cols,
                index=default_idx,
                key=f"map_{var}",
            )
        st.success("All placeholders mapped.  Auto-filled vars need no mapping.")
elif df is not None and not mappable_vars:
    st.info(
        "No placeholders to map.  Add `{{placeholders}}` to subject/body if needed."
    )
elif df is None and mappable_vars:
    st.info("Upload an Excel file to enable variable mapping.")

# ── 4. Attachment ──

with st.expander("📎 4. Attachment (Optional)", expanded=False):
    attached = st.file_uploader(
        "Upload a file to attach to every email",
        type=["pdf", "docx", "png", "jpg", "jpeg"],
        key="attachment_upload",
    )
    if attached:
        st.session_state.attachment_bytes = attached.read()
        st.session_state.attachment_name = attached.name
        st.success(
            f"📎 `{attached.name}` ({len(st.session_state.attachment_bytes):,} bytes)"
        )
    else:
        st.session_state.attachment_bytes = None
        st.session_state.attachment_name = None

# ── 5. Send Emails ──

st.divider()
st.subheader("🚀 5. Send Emails")

# Validation
missing = []
if not st.session_state.api_key:
    missing.append("Brevo API Key")
if st.session_state.get("df") is None:
    missing.append("Excel data")
else:
    if find_email_column(st.session_state.df) is None:
        missing.append("**Email** column in Excel")
if not st.session_state.subject.strip():
    missing.append("Email Subject")
if not st.session_state.body.strip():
    missing.append("Email Body")
if mappable_vars:
    unmapped = [v for v in mappable_vars if f"map_{v}" not in st.session_state]
    if unmapped:
        missing.append(f"Mapping for {', '.join(f'{{{{{v}}}}}' for v in unmapped)}")
if st.session_state.get("sending"):
    missing.append("(sending in progress…)")

if missing:
    st.warning(f"⏳ {', '.join(missing)}")

send_disabled = bool(missing)

send_btn = st.button(
    "📤 Send Emails",
    disabled=send_disabled,
    type="primary",
    use_container_width=True,
)

if send_btn:
    st.session_state.sending = True
    st.session_state.results = []
    df = st.session_state.df
    total = len(df)
    sender = {
        "name": st.session_state.sender_name,
        "email": st.session_state.sender_email,
    }

    email_col = find_email_column(df) or "Email"
    name_col = find_name_column(df)

    progress_bar = st.progress(0)
    status_text = st.empty()
    log_placeholder = st.code("", language="text")
    log_lines = []

    for idx, (_, row) in enumerate(df.iterrows()):
        email = str(row.get(email_col, "")).strip()
        name_val = str(row.get(name_col, "")).strip() if name_col else ""

        # ── Skip blank emails ──
        if not email:
            st.session_state.results.append(
                {
                    "Name": name_val or "(unnamed)",
                    "Email": "(blank)",
                    "Status": "⏭️ Skipped",
                    "Error": "No email address",
                }
            )
            log_lines.append(
                f"[{idx + 1}/{total}] ⏭️  {name_val or '(unnamed)'} "
                f"— blank email, skipped"
            )
            log_placeholder.code("\n".join(log_lines), language="text")
            progress_bar.progress((idx + 1) / total)
            status_text.text(f"[{idx + 1}/{total}] ⏭️  Skipped {name_val or 'unnamed'}")
            continue

        # ── Build replacements ──
        replacements = {
            "mailing_name": st.session_state.mailing_name,
            "sender_name": sender["name"],
            "sender_email": sender["email"],
        }
        for var in mappable_vars:
            col = st.session_state.get(f"map_{var}")
            if col:
                replacements[var] = str(row.get(col, "")).strip()

        # ── Fill templates (replace {{var}} with values) ──
        subject_filled = st.session_state.subject
        body_filled = st.session_state.body
        for var, val in replacements.items():
            placeholder = f"{{{{{var}}}}}"
            subject_filled = subject_filled.replace(placeholder, val)
            body_filled = body_filled.replace(placeholder, val)

        # Warn about any placeholders left unreplaced
        unreplaced = detect_placeholders(subject_filled + body_filled)
        if unreplaced:
            names = ", ".join(f"{{{{{v}}}}}" for v in unreplaced)
            st.session_state.results.append(
                {
                    "Name": name_val or email.split("@")[0],
                    "Email": email,
                    "Status": "❌ Failed",
                    "Error": f"Unmapped placeholder(s): {names}",
                }
            )
            log_lines.append(
                f"[{idx + 1}/{total}] ❌  {name_val or email} "
                f"<{email}> — unmapped {names}"
            )
            log_placeholder.code("\n".join(log_lines), language="text")
            progress_bar.progress((idx + 1) / total)
            status_text.text(
                f"[{idx + 1}/{total}] ❌  {name_val or email} — unmapped placeholders"
            )
            continue

        html_body = body_to_html(body_filled)

        # ── Send ──
        status_text.text(f"[{idx + 1}/{total}] 📤  Sending to {name_val or email}...")
        success, error = send_brevo(
            api_key=st.session_state.api_key,
            sender=sender,
            to_email=email,
            to_name=name_val,
            subject=subject_filled,
            html_body=html_body,
            attachment_bytes=st.session_state.get("attachment_bytes"),
            attachment_name=st.session_state.get("attachment_name"),
        )

        if success:
            st.session_state.results.append(
                {
                    "Name": name_val or email.split("@")[0],
                    "Email": email,
                    "Status": "✅ Sent",
                    "Error": "",
                }
            )
            log_lines.append(
                f"[{idx + 1}/{total}] ✅  {name_val or email} <{email}> — sent"
            )
            status_text.text(f"[{idx + 1}/{total}] ✅  {name_val or email} — sent")
        else:
            st.session_state.results.append(
                {
                    "Name": name_val or email.split("@")[0],
                    "Email": email,
                    "Status": "❌ Failed",
                    "Error": error,
                }
            )
            log_lines.append(
                f"[{idx + 1}/{total}] ❌  {name_val or email} <{email}> — {error}"
            )
            status_text.text(f"[{idx + 1}/{total}] ❌  {name_val or email} — failed")

        log_placeholder.code("\n".join(log_lines), language="text")
        progress_bar.progress((idx + 1) / total)

        # ── Delay (except after last) ──
        if idx < total - 1:
            time.sleep(st.session_state.delay)

    st.session_state.sending = False


# ── 6. Results ──

if st.session_state.get("results"):
    st.divider()
    st.subheader("📊 Results")

    rdf = pd.DataFrame(st.session_state.results)
    st.dataframe(rdf, use_container_width=True, hide_index=True)

    sent = sum(1 for r in st.session_state.results if r["Status"] == "✅ Sent")
    failed = sum(1 for r in st.session_state.results if r["Status"] == "❌ Failed")
    skipped = sum(1 for r in st.session_state.results if r["Status"] == "⏭️ Skipped")
    total = len(st.session_state.results)

    mc = st.columns(4)
    mc[0].metric("Total", total)
    mc[1].metric("✅ Sent", sent)
    mc[2].metric("❌ Failed", failed)
    mc[3].metric("⏭️ Skipped", skipped)

    if st.button("Clear Results"):
        st.session_state.results = []
        st.rerun()
