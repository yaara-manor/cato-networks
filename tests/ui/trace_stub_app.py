"""Minimal Streamlit script: the trace panel for the conversation id in the query string (what 42 embeds too)."""

from uuid import UUID

import psycopg
import streamlit as st

from core.config import settings
from storage import StateStore
from ui.trace_panel import TracePanel, render_trace_panel

with psycopg.connect(settings.database_url, autocommit=True) as connection:
    replay = StateStore(connection).replay_trace(UUID(st.query_params["cid"]))
assert replay is not None
render_trace_panel(TracePanel.from_replay(replay))
