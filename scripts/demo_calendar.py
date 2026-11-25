import argparse
import asyncio
from zoneinfo import ZoneInfo

from sqlalchemy import select

from agent.config import Settings, get_settings
from agent.core.clock import SystemClock
from agent.core.service import GoalService
from agent.db.session import get_engine, get_sessionmaker
from agent.executors.local_calendar import LocalCalendarExecutor
from agent.executors.registry import ExecutorRegistry
from agent.llm.base import LLMClient
from agent.llm.factory import get_llm
from agent.llm.fake import FakeLLMClient
from agent.models import Base, Task, User

DEMO_EMAIL = "demo@example.com"

CANNED_RESPONSES = [
    '{"title": "Prepare the quarterly report", "deadline": "tomorrow", '
    '"constraints": {"earliest_time": "00:00", "latest_time": "23:59", '
    '"preferred_days": [], "max_session_minutes": 60, "notes": ""}, '
    '"clarifying_question": null}',
    '{"tasks": ['
    '{"description": "Draft the outline", "estimated_effort_minutes": 30, '
    '"action_type": "focus", "order": 1},'
    '{"description": "Review and polish", "estimated_effort_minutes": 20, '
    '"action_type": "focus", "order": 2}'
    ']}',
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a local calendar plan from a goal")
    parser.add_argument("--goal", help="Goal text, otherwise the script prompts for it")
    parser.add_argument(
        "--fake",
        action="store_true",
        help="Use canned offline responses instead of the configured LLM",
    )
    return parser


def build_llm(settings: Settings) -> LLMClient:
    if settings.llm_provider == "fake":
        return FakeLLMClient(CANNED_RESPONSES)
    return get_llm(settings)


async def run_demo(goal_text: str, settings: Settings) -> int:
    engine = get_engine(settings.database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    maker = get_sessionmaker(settings.database_url)
    registry = ExecutorRegistry()
    registry.register("focus", LocalCalendarExecutor(maker))
    llm = build_llm(settings)

    async with maker() as session:
        result = await session.execute(select(User).where(User.email == DEMO_EMAIL))
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                name="Demo User",
                email=DEMO_EMAIL,
                timezone=settings.timezone,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

        service = GoalService(session, registry, SystemClock())
        outcome = await service.create_goal_plan(user, goal_text, "general", llm)

        if outcome.clarifying_question:
            print(f"Need more detail: {outcome.clarifying_question}")
            return 0

        tasks_result = await session.execute(
            select(Task).where(Task.goal_id == outcome.goal.id)
        )
        descriptions = {task.id: task.description for task in tasks_result.scalars().all()}

        print(f"Goal: {outcome.goal.extracted_goal}")
        print(f"Status: {outcome.goal.status.value}")
        if outcome.schedule is None or not outcome.schedule.actions:
            print("No actions were scheduled")
            if outcome.schedule is not None and outcome.schedule.failure is not None:
                print(f"Reason: {outcome.schedule.failure.reason}")
            return 0

        zone = ZoneInfo(user.timezone)
        print("Scheduled actions:")
        for number, action in enumerate(outcome.schedule.actions, start=1):
            local_time = action.scheduled_at.astimezone(zone).strftime("%Y-%m-%d %H:%M %Z")
            description = descriptions.get(action.task_id, "Task")
            print(f"{number}. {local_time} | {action.duration_minutes} min | {description}")
            print(f"   external ref: {action.external_ref}")
        return 0


def main() -> int:
    args = build_parser().parse_args()
    goal_text = args.goal or input("Goal: ").strip()
    if not goal_text:
        print("Goal text cannot be empty")
        return 2

    settings = get_settings()
    if args.fake:
        settings = settings.model_copy(update={"llm_provider": "fake"})
    return asyncio.run(run_demo(goal_text, settings))


if __name__ == "__main__":
    raise SystemExit(main())
