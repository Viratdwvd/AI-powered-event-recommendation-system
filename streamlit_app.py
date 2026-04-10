"""
streamlit_app.py  —  VIT Event Recommender  (live-scrape edition)
=================================================================
Architecture:
  VIT EventHub website
       │  HTTP GET (requests + BeautifulSoup)
       ▼
  app/scraper.py  ──►  list[dict]  (scraped events)
       │
       ▼
  event_storage.py  ──►  SQLite  (events + scrape_meta)
       │
       ▼
  vector_store.py  ──►  FAISS in-memory index
       │
       ▼
  recommender.py  ──►  ranked event_ids  ──►  UI cards
                                          └──►  email_service.py

Admin is password-gated.  Students never see the admin tab internals.
Past events are filtered out everywhere.
Links are validated before rendering.
"""

import os
from datetime import date, datetime, timezone
import streamlit as st
import pandas as pd

# ── Page config — must be FIRST ───────────────────────────────────────────────
st.set_page_config(
    page_title="VIT Event Recommender",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:ital,wght@0,300;0,400;0,500;1,400&display=swap');

html,body,[class*="css"]      { font-family:'DM Sans',sans-serif; }
h1,h2,h3,h4                   { font-family:'Syne',sans-serif !important; }
section[data-testid="stSidebar"]   { background:#0d0d1c; }
section[data-testid="stSidebar"] * { color:#e2e2f0 !important; }
.main .block-container         { padding-top:1.6rem; max-width:1080px; }

/* ── Hero ── */
.hero {
  background:linear-gradient(135deg,#1e1b4b 0%,#4338ca 50%,#7c3aed 100%);
  border-radius:16px; padding:32px 40px; margin-bottom:24px; color:#fff;
  position:relative; overflow:hidden;
}
.hero::after {
  content:''; position:absolute; right:-40px; top:-40px;
  width:220px; height:220px; border-radius:50%;
  background:rgba(255,255,255,.05);
}
.hero h1  { font-size:28px; margin:0 0 6px; }
.hero p   { margin:0; opacity:.82; font-size:13.5px; }
.live-dot {
  display:inline-block; width:9px; height:9px; border-radius:50%;
  background:#34d399; margin-right:6px;
  box-shadow:0 0 0 3px rgba(52,211,153,.3);
  animation:pulse 1.8s ease-in-out infinite;
}
@keyframes pulse { 0%,100%{box-shadow:0 0 0 3px rgba(52,211,153,.3)}
                   50%{box-shadow:0 0 0 7px rgba(52,211,153,.08)} }

/* ── Event card ── */
.event-card {
  background:#fff; border:1px solid #e4e4f0; border-radius:14px;
  padding:18px 22px; margin-bottom:12px; position:relative;
  transition:box-shadow .18s,transform .18s;
}
.event-card:hover { box-shadow:0 6px 22px rgba(79,70,229,.13); transform:translateY(-1px); }
.event-card h4    { margin:6px 0 5px; font-size:15.5px; color:#1a1a2e; }
.event-card p     { margin:0; font-size:13px; color:#555; line-height:1.65; }
.meta-row         { font-size:12px; color:#888; margin-top:9px; display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
.reg-btn {
  display:inline-block; padding:4px 13px; border-radius:20px;
  background:#4338ca; color:#fff !important; font-size:12px;
  font-weight:600; text-decoration:none !important; line-height:1.8;
}
.reg-btn:hover           { background:#3730a3; }
.no-link-badge           { display:inline-block; padding:3px 11px; border-radius:20px; background:#f3f4f6; color:#6b7280; font-size:11px; }
.badge                   { display:inline-block; padding:2px 10px; border-radius:20px; font-size:11px; font-weight:600; }
.rank-badge {
  position:absolute; top:14px; right:14px;
  background:#4338ca; color:#fff; border-radius:50%;
  width:26px; height:26px; display:flex; align-items:center;
  justify-content:center; font-size:11px; font-weight:700;
}
.days-pill { display:inline-block; padding:2px 8px; border-radius:20px; background:#ecfdf5; color:#065f46; font-size:11px; font-weight:600; }
.live-source { display:inline-block; padding:2px 8px; border-radius:20px; background:#ede9fe; color:#5b21b6; font-size:10px; font-weight:600; }

/* ── Stat card ── */
.stat-card { background:rgba(255,255,255,.08); border-radius:11px; padding:14px 18px; text-align:center; border:1px solid rgba(255,255,255,.12); }
.stat-card .num { font-size:28px; font-weight:800; color:#a5b4fc; font-family:'Syne',sans-serif; }
.stat-card .lbl { font-size:11px; color:#94a3b8; margin-top:1px; }

/* ── Sync status bar ── */
.sync-bar { background:#1e1b4b; border:1px solid #312e81; border-radius:10px; padding:10px 16px; font-size:12.5px; color:#c7d2fe; margin-bottom:16px; }
.sync-bar b { color:#a5b4fc; }

/* ── Admin gate ── */
.admin-gate { max-width:360px; margin:50px auto; text-align:center; background:#fff; border:1px solid #e4e4f0; border-radius:16px; padding:34px; }
.admin-gate h3 { margin:0 0 6px; }
.admin-gate p  { font-size:13px; color:#666; margin-bottom:18px; }

/* ── Misc ── */
button[data-baseweb="tab"] { font-family:'Syne',sans-serif !important; font-weight:600; }
div[data-testid="stAlert"] { border-radius:10px; }
</style>
""", unsafe_allow_html=True)

# ── App imports (after page-config) ──────────────────────────────────────────
from app.database     import create_tables
from app.scraper      import scrape_eventhub, ScrapeResult
from app.event_storage import save_events, get_all_events, save_scrape_meta, get_last_scrape_meta
from app.recommender  import recommend_for_user
from app.user_service import register_or_update_user, get_all_users, get_user
from app.vector_store import get_vector_store
from app.email_service import send_email, fetch_events_by_ids
from app.feedback     import save_feedback

# ── Bootstrap (runs once per cold start) ─────────────────────────────────────
@st.cache_resource(show_spinner="Initialising database…")
def _init_db():
    create_tables()
    return True

_init_db()

# ── Session-state defaults ────────────────────────────────────────────────────
for key, val in [("admin_auth", False), ("last_scrape_result", None)]:
    if key not in st.session_state:
        st.session_state[key] = val

# ── Constants ─────────────────────────────────────────────────────────────────
TODAY = date.today()

CATEGORY_COLORS = {
    "Hackathon":   ("#fef3c7","#92400e"),
    "Workshop":    ("#dbeafe","#1e40af"),
    "Seminar":     ("#dcfce7","#166534"),
    "Talk":        ("#fce7f3","#9d174d"),
    "Competition": ("#ede9fe","#5b21b6"),
    "Sports":      ("#ffedd5","#9a3412"),
    "Cultural":    ("#fdf4ff","#86198f"),
    "Meetup":      ("#f0fdf4","#15803d"),
    "Bootcamp":    ("#fef9c3","#854d0e"),
    "Conference":  ("#e0f2fe","#075985"),
    "Exhibition":  ("#fdf2f8","#9d174d"),
    "Fest":        ("#fdf4ff","#7e22ce"),
    "Championship":("#ffedd5","#9a3412"),
    "Sprint":      ("#dcfce7","#14532d"),
    "Olympiad":    ("#ede9fe","#4c1d95"),
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_upcoming(event: dict) -> bool:
    raw = (event.get("date") or "").strip()
    if not raw:
        return True
    try:
        return datetime.strptime(raw[:10], "%Y-%m-%d").date() >= TODAY
    except ValueError:
        return True

def _days_until(event: dict) -> int | None:
    raw = (event.get("date") or "").strip()
    try:
        return (datetime.strptime(raw[:10], "%Y-%m-%d").date() - TODAY).days
    except ValueError:
        return None

def _link_ok(url) -> bool:
    return bool(url and str(url).startswith("http") and "." in str(url))

def _badge(cat: str) -> str:
    bg, fg = CATEGORY_COLORS.get(cat, ("#f3f4f6","#374151"))
    return f'<span class="badge" style="background:{bg};color:{fg};">{cat or "Event"}</span>'

def _time_ago(iso: str) -> str:
    try:
        dt  = datetime.fromisoformat(iso)
        sec = int((datetime.now() - dt).total_seconds())
        if sec < 60:   return "just now"
        if sec < 3600: return f"{sec//60}m ago"
        if sec < 86400:return f"{sec//3600}h ago"
        return f"{sec//86400}d ago"
    except Exception:
        return iso

def render_event_card(event: dict, rank: int | None = None):
    rank_html  = f'<div class="rank-badge">#{rank}</div>' if rank else ""
    days       = _days_until(event)
    days_html  = f'<span class="days-pill">in {days}d</span>' if (days is not None and 0 <= days <= 60) else ""
    src_html   = '<span class="live-source">● LIVE</span>' if event.get("source") == "eventhub_live" else ""

    action_html = (
        f'<a class="reg-btn" href="{event["link"]}" target="_blank" rel="noopener">→ Register</a>'
        if _link_ok(event.get("link"))
        else '<span class="no-link-badge">Link coming soon</span>'
    )
    desc = (event.get("description") or "")
    if len(desc) > 180: desc = desc[:177] + "…"

    st.markdown(f"""
    <div class="event-card">
      {rank_html}
      {_badge(event.get("category",""))} {src_html}
      <h4>{event["title"]}</h4>
      <p>{desc}</p>
      <div class="meta-row">📅&nbsp;{event.get("date","TBA")} {days_html} {action_html}</div>
    </div>
    """, unsafe_allow_html=True)

def upcoming_only(events):
    return [e for e in events if _is_upcoming(e)]

def _do_scrape_and_index() -> ScrapeResult:
    """Scrape → save → rebuild index.  Returns the ScrapeResult."""
    result = scrape_eventhub()
    save_scrape_meta(result.status, len(result.events), result.message)

    if result.status == "ok" and result.events:
        save_events(result.events)
        get_vector_store().build()

    return result

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🎓 VIT Events")
    st.markdown("---")

    all_events_raw = get_all_events()
    all_events     = upcoming_only(all_events_raw)
    all_users      = get_all_users()
    meta           = get_last_scrape_meta()

    # Sync status
    if meta:
        colour = "#34d399" if meta["status"] == "ok" else "#f87171"
        st.markdown(
            f'<div class="sync-bar">'
            f'<span style="color:{colour};">●</span> '
            f'Last synced <b>{_time_ago(meta["scraped_at"])}</b> · '
            f'<b>{meta["event_count"]}</b> events fetched'
            f'</div>',
            unsafe_allow_html=True
        )
    else:
        st.markdown('<div class="sync-bar">⚪ Not yet synced with EventHub</div>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f'<div class="stat-card"><div class="num">{len(all_events)}</div><div class="lbl">Upcoming</div></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="stat-card"><div class="num">{len(all_users)}</div><div class="lbl">Students</div></div>', unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("#### 👤 My Profile")
    sidebar_email     = st.text_input("Email", placeholder="you@vit.ac.in", key="sidebar_email")
    sidebar_interests = st.text_input("Interests", placeholder="ML, robotics, CTF…", key="sidebar_interests")

    if st.button("💾 Save", use_container_width=True):
        if sidebar_email and sidebar_interests:
            register_or_update_user(sidebar_email, sidebar_interests)
            st.success("Saved!")
        else:
            st.warning("Fill both fields.")

    if sidebar_email:
        u = get_user(sidebar_email)
        if u:
            st.caption(f"✅ *{u['interests']}*")

    st.markdown("---")
    st.caption("Data source: eventhubcc.vit.ac.in\nPowered by FAISS · SentenceTransformers")


# ── Main ──────────────────────────────────────────────────────────────────────
# Sync bar visible to all users (read-only info)
if meta and meta["status"] == "ok":
    st.markdown(f"""
    <div class="hero">
      <h1>🎓 VIT Event Recommender</h1>
      <p><span class="live-dot"></span>Live data from <b>eventhubcc.vit.ac.in</b> · 
         Last synced {_time_ago(meta["scraped_at"])} · 
         {len(all_events)} upcoming events indexed</p>
    </div>
    """, unsafe_allow_html=True)
elif meta and meta["status"] in ("js_required","error"):
    st.markdown("""
    <div class="hero">
      <h1>🎓 VIT Event Recommender</h1>
      <p>⚠️ EventHub sync issue — showing cached events. Admin can retry from the Admin tab.</p>
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
    <div class="hero">
      <h1>🎓 VIT Event Recommender</h1>
      <p>AI-powered personalised event discovery · Semantic similarity · FAISS</p>
    </div>
    """, unsafe_allow_html=True)

tab_rec, tab_browse, tab_admin, tab_about = st.tabs([
    "✨ Recommendations", "📋 Browse Events", "⚙️ Admin", "ℹ️ About"
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1  —  RECOMMENDATIONS
# ══════════════════════════════════════════════════════════════════════════════
with tab_rec:
    st.subheader("Get Personalised Recommendations")

    if not all_events:
        st.info("No events available yet — the admin needs to sync data from EventHub first.")
    else:
        cl, cr = st.columns([2, 1])
        with cl:
            rec_email = st.text_input("Your email",
                value=st.session_state.get("sidebar_email",""),
                placeholder="you@vit.ac.in", key="rec_email")
            rec_interests = st.text_area("Your interests",
                value=st.session_state.get("sidebar_interests",""),
                placeholder="machine learning, web dev, hackathons, cricket…",
                height=88, key="rec_interests")
        with cr:
            top_k     = st.slider("# of results", 3, 10, 5)
            send_mail = st.checkbox("📧 Email me results")
            st.caption("Only **upcoming** events from EventHub are shown.")

        if st.button("🔍 Find My Events", type="primary", use_container_width=True):
            if not rec_email or not rec_interests:
                st.warning("Enter your email and interests.")
            elif not get_vector_store().is_built:
                st.error("Index not built. Ask the admin to sync EventHub data.")
            else:
                with st.spinner("Finding your events…"):
                    register_or_update_user(rec_email, rec_interests)
                    recs = recommend_for_user(rec_email, rec_interests, top_k=top_k*3)

                events_data  = fetch_events_by_ids(recs)
                events_map   = {e["event_id"]: e for e in events_data}
                upcoming_ids = [eid for eid in recs if eid in events_map and _is_upcoming(events_map[eid])][:top_k]

                if not upcoming_ids:
                    st.info("No upcoming events match your interests right now. Try different keywords!")
                else:
                    st.success(f"Found **{len(upcoming_ids)}** upcoming events for you!")
                    for rank, eid in enumerate(upcoming_ids, 1):
                        render_event_card(events_map[eid], rank=rank)

                    # Rating
                    st.markdown("---")
                    st.markdown("#### 🌟 Rate a recommendation")
                    fb_map = {events_map[e]["title"]: e for e in upcoming_ids}
                    chosen = st.selectbox("Event", list(fb_map.keys()))
                    stars  = st.select_slider("Rating", [1,2,3,4,5], format_func=lambda x:"⭐"*x)
                    if st.button("Submit Rating"):
                        save_feedback(rec_email, fb_map[chosen], stars)
                        st.success("Rating saved — it improves your future recommendations!")

                    if send_mail:
                        with st.spinner("Sending email…"):
                            try:
                                ok = send_email(rec_email, upcoming_ids)
                                st.success("📧 Email sent!") if ok else st.warning("Email delivery failed.")
                            except ValueError as e:
                                st.error(str(e))


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2  —  BROWSE
# ══════════════════════════════════════════════════════════════════════════════
with tab_browse:
    st.subheader("All Upcoming Events from EventHub")

    if meta and meta["status"] == "ok":
        st.caption(f"📡 Live data · synced {_time_ago(meta['scraped_at'])}")
    elif not all_events:
        st.warning("No events loaded. The admin needs to sync from EventHub first.")

    if all_events:
        df = pd.DataFrame(all_events)

        cs, cc, csort = st.columns([3,1,1])
        with cs:
            q = st.text_input("🔎 Search", placeholder="hackathon, python, sports…")
        with cc:
            cats = ["All"] + sorted(df["category"].dropna().unique().tolist())
            cat  = st.selectbox("Category", cats)
        with csort:
            sort_by = st.selectbox("Sort", ["Date ↑","Title A–Z"])

        filt = df.copy()
        if q:
            filt = filt[
                filt["title"].str.contains(q, case=False, na=False) |
                filt["description"].str.contains(q, case=False, na=False)
            ]
        if cat != "All":
            filt = filt[filt["category"] == cat]
        filt = filt.sort_values("date" if sort_by=="Date ↑" else "title",
                                 ascending=True, na_position="last")

        st.caption(f"Showing **{len(filt)}** of **{len(df)}** upcoming events")
        for _, row in filt.iterrows():
            render_event_card(row.to_dict())


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3  —  ADMIN  (password-gated)
# ══════════════════════════════════════════════════════════════════════════════
with tab_admin:
    if not st.session_state.admin_auth:
        st.markdown("""
        <div class="admin-gate">
          <h3>🔒 Admin Access</h3>
          <p>This panel is restricted to administrators.</p>
        </div>
        """, unsafe_allow_html=True)
        _, mid, _ = st.columns([1,2,1])
        with mid:
            pwd = st.text_input("Password", type="password", key="admin_pwd")
            if st.button("Unlock", type="primary", use_container_width=True):
                correct = (
                    st.secrets.get("ADMIN_PASSWORD", None)
                    or os.getenv("ADMIN_PASSWORD", "vit@admin2026")
                )
                if pwd == correct:
                    st.session_state.admin_auth = True
                    st.rerun()
                else:
                    st.error("Incorrect password.")
    else:
        # ── Authenticated ──────────────────────────────────────────────────
        st.subheader("⚙️ Admin Panel")
        if st.button("🔓 Lock Panel", type="secondary"):
            st.session_state.admin_auth = False
            st.rerun()

        st.markdown("---")

        # ── ROW 1: Scrape controls + status ───────────────────────────────
        col_scrape, col_status = st.columns([1, 1])

        with col_scrape:
            st.markdown("#### 🌐 EventHub Live Sync")
            st.markdown(
                "Fetches the latest events directly from "
                "**eventhubcc.vit.ac.in/EventHub/** using HTTP scraping, "
                "embeds them, and rebuilds the recommendation index."
            )

            if st.button("🔄 Fetch & Index from EventHub", type="primary", use_container_width=True):
                with st.spinner("Connecting to EventHub and scraping events…"):
                    result = _do_scrape_and_index()
                    st.session_state.last_scrape_result = result

                if result.status == "ok":
                    st.success(f"✅ **{len(result.events)} events** fetched and indexed in {result.duration_s:.1f}s")
                    st.cache_resource.clear()
                    st.rerun()
                elif result.status == "js_required":
                    st.error("⚠️ EventHub is a JavaScript app — it requires a browser to render.")
                    st.warning(result.message)
                    st.info(
                        "**Fix:** Add `packages.txt` to your repo with:\n```\nchromium\nchromium-driver\n```\n"
                        "Then re-deploy on Streamlit Cloud. Or contact VIT IT for an API endpoint."
                    )
                elif result.status == "empty":
                    st.warning(f"⚠️ {result.message}")
                else:
                    st.error(f"❌ Scrape failed: {result.message}")
                    st.info(
                        "**Possible reasons:**\n"
                        "- EventHub is on VIT's intranet and requires VPN / campus network\n"
                        "- The site is temporarily down\n"
                        "- SSL certificate issue\n\n"
                        "The app will continue serving the **last successfully scraped events** from the database."
                    )

        with col_status:
            st.markdown("#### 📊 Sync Status")
            meta2 = get_last_scrape_meta()
            vs    = get_vector_store()

            if meta2:
                status_colour = {"ok":"🟢","js_required":"🟡","empty":"🟡","error":"🔴"}.get(meta2["status"],"⚪")
                st.markdown(f"""
                | Field | Value |
                |-------|-------|
                | Status | {status_colour} `{meta2["status"]}` |
                | Last sync | {_time_ago(meta2["scraped_at"])} |
                | Events fetched | {meta2["event_count"]} |
                | Upcoming (shown) | {len(upcoming_only(get_all_events()))} |
                | FAISS index | {"✅ Built" if vs.is_built else "⚠️ Not built"} |
                """)
                if meta2.get("message"):
                    st.caption(f"Message: {meta2['message'][:200]}")
            else:
                st.info("No sync attempted yet.")

            if vs.is_built and st.button("🔄 Rebuild Index Only (no re-scrape)"):
                with st.spinner("Rebuilding index from DB…"):
                    n = get_vector_store().build()
                st.success(f"Rebuilt — {n} events indexed")

        # ── ROW 2: Registered students ────────────────────────────────────
        st.markdown("---")
        st.markdown("#### 👥 Registered Students")
        users = get_all_users()
        if users:
            udf = pd.DataFrame(users, columns=["Email","Interests"])
            st.dataframe(udf, use_container_width=True, hide_index=True)
            st.caption(f"{len(users)} registered student(s)")
        else:
            st.info("No students registered yet.")

        # ── ROW 3: Email ──────────────────────────────────────────────────
        st.markdown("---")
        st.markdown("#### 📧 Email Notification Status")
        email_ok = bool(os.getenv("SENDER_EMAIL")) and bool(os.getenv("SENDER_PASSWORD"))
        if email_ok:
            st.success("✅ Email credentials configured.")
        else:
            st.warning(
                "Email not configured. Add `SENDER_EMAIL` and `SENDER_PASSWORD` "
                "to Streamlit Cloud **Secrets** to enable email notifications."
            )

        # ── ROW 4: Raw event table (admin only) ────────────────────────────
        st.markdown("---")
        st.markdown("#### 🗃️ All Events in Database")
        all_ev = get_all_events()
        if all_ev:
            ev_df = pd.DataFrame(all_ev).drop(columns=["source"], errors="ignore")
            ev_df["upcoming"] = ev_df.apply(lambda r: "✅" if _is_upcoming(r.to_dict()) else "❌ past", axis=1)
            st.dataframe(ev_df[["title","category","date","upcoming","link"]], use_container_width=True, hide_index=True)
        else:
            st.info("Database is empty.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4  —  ABOUT
# ══════════════════════════════════════════════════════════════════════════════
with tab_about:
    st.markdown("""
    ## About VIT Event Recommender

    Personalised event discovery powered by **live scraping** of
    [eventhubcc.vit.ac.in/EventHub](https://eventhubcc.vit.ac.in/EventHub/)
    and **semantic similarity search** — not keyword matching.

    ### Live Architecture
    ```
    VIT EventHub Website
         │  HTTP GET (requests + BeautifulSoup)
         │  Multiple CSS selector strategies + regex extraction
         ▼
    app/scraper.py  ──►  list of parsed events
         │
         ▼
    SQLite Database  (events + scrape_meta + users + feedback)
         │
         ▼
    FAISS Vector Index  (384-dim all-MiniLM-L6-v2 embeddings)
         │
         ▼
    Recommender  (85% semantic similarity + 15% feedback boost)
         │
    ┌────┴────┐
    ▼         ▼
    Streamlit   Gmail SMTP
    UI Cards    Email
    ```

    ### Data Flow
    1. **Scrape** — Admin triggers HTTP fetch from EventHub; page is parsed with
       4-strategy BeautifulSoup selector cascade
    2. **Extract** — Title, description, date (regex), category (keyword regex), link per event
    3. **Embed** — Each event → 384-dim vector via `all-MiniLM-L6-v2`
    4. **Index** — FAISS IndexFlatL2 stores all embeddings for sub-ms search
    5. **Filter** — Past events (date < today) are always hidden from students
    6. **Recommend** — User interest text is embedded and nearest events are retrieved,
       then re-ranked by `0.85 × similarity + feedback_boost`
    7. **Deliver** — Cards in UI + optional email via Gmail SMTP

    ### Tech Stack
    | Layer | Technology |
    |-------|-----------|
    | UI | Streamlit |
    | Scraping | `requests` + `BeautifulSoup4` + `lxml` |
    | Embeddings | `sentence-transformers` · `all-MiniLM-L6-v2` |
    | Vector Search | FAISS (CPU) |
    | Database | SQLite 3 |
    | Email | `smtplib` + Gmail SMTP |

    ### If EventHub uses JavaScript rendering
    The scraper gracefully detects JS-only pages and shows a clear error.
    Fix: add a `packages.txt` with `chromium` and `chromium-driver` to your
    GitHub repo before deploying on Streamlit Cloud.

    ---
    **Author:** Virat Dwivedi · VIT Event Recommender
    """)
