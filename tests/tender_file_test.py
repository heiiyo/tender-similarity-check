import pytest

from apps.service.tender_compliance_service import parser_tender_topic

@pytest.fixture
def context():
    from apps import AppContext
    return AppContext().init_context()


@pytest.mark.asyncio
async def test_parser_tender_topic(context):
     result = await parser_tender_topic(1)
     print(result)