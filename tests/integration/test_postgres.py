"""Real PostgreSQL-only concurrency regression, executed by CI service."""
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import pytest
from test_api import client, auth, fake_recommendation
from campus_assistant.providers import llm
from campus_assistant.api.db import AIBudget, AIRun
from sqlalchemy import select

pytestmark=pytest.mark.skipif(not os.getenv('TEST_DATABASE_URL','').startswith('postgresql'),reason='requires real PostgreSQL')

def test_postgres_budget_reservation_serializes(client,monkeypatch):
    c,factory=client;headers=auth(c)
    monkeypatch.setenv('AI_PROVIDER','ollama');monkeypatch.setenv('AI_MODEL','test-local')
    monkeypatch.setenv('AI_INPUT_IDR_PER_MILLION','1000000');monkeypatch.setenv('AI_OUTPUT_IDR_PER_MILLION','1000000')
    monkeypatch.setenv('AI_MAX_RUN_IDR','10000')
    # Both students have complete evidence; each reservation exceeds half this budget.
    monkeypatch.setenv('AI_MONTHLY_CLASS_IDR','5000')
    entered=threading.Event();release=threading.Event()
    def generate(settings,messages,gaps):
        entered.set()
        assert release.wait(timeout=10)
        return fake_recommendation(gaps),10,20
    monkeypatch.setattr(llm,'generate',generate)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(c.post,'/classes/RPL-01/interventions/ai',headers=headers,json={'student_id':'STD-003','idempotency_key':'pg-first-run'})
        assert entered.wait(timeout=5)
        try:
            second=c.post('/classes/RPL-01/interventions/ai',headers=headers,json={'student_id':'STD-004','idempotency_key':'pg-second-run'})
            assert second.status_code==409
        finally:release.set()
        assert first.result(timeout=10).status_code==201
    with factory() as db:
        runs=db.scalars(select(AIRun)).all()
        budget=db.scalars(select(AIBudget)).one()
        assert len(runs)==1 and budget.committed_idr==runs[0].cost_idr
