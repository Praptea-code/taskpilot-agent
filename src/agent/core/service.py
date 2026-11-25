from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from agent.core.clock import Clock
from agent.core.decomposer import decompose_goal
from agent.core.extractor import extract_goal
from agent.core.scheduler import ScheduleResult, SchedulingRequest, schedule_tasks
from agent.executors.registry import ExecutorRegistry
from agent.llm.base import LLMClient
from agent.llm.factory import get_llm
from agent.models import ActionStatus, Goal, GoalStatus, Task, TaskStatus, User


@dataclass(frozen=True)
class PlanOutcome:
    goal: Goal
    clarifying_question: str | None
    schedule: ScheduleResult | None


class GoalService:
    def __init__(self, session: AsyncSession, registry: ExecutorRegistry, clock: Clock) -> None:
        self.session = session
        self.registry = registry
        self.clock = clock

    async def create_goal_plan(
        self,
        user: User,
        raw_text: str,
        domain: str,
        llm: LLMClient | None = None,
        goal: Goal | None = None,
    ) -> PlanOutcome:
        engine = llm or get_llm()
        extraction = await extract_goal(raw_text, user, self.clock, engine)
        if goal is None:
            goal = Goal(
                user_id=user.id,
                raw_input_text=raw_text,
                extracted_goal=extraction.title,
                deadline=extraction.deadline,
                constraints=extraction.constraints,
                status=GoalStatus.PENDING,
                domain=domain,
            )
            self.session.add(goal)
            await self.session.flush()
        else:
            goal.raw_input_text = raw_text
            goal.extracted_goal = extraction.title
            goal.deadline = extraction.deadline
            goal.constraints = extraction.constraints
            goal.domain = domain
            goal.status = GoalStatus.PENDING

        if extraction.clarifying_question:
            goal.status = GoalStatus.NEEDS_INFO
            await self.session.commit()
            return PlanOutcome(goal, extraction.clarifying_question, None)

        decomposed = await decompose_goal(
            extraction.title,
            extraction.constraints,
            self.clock,
            engine,
            user.timezone,
        )
        task_rows: list[Task] = []
        for item in decomposed:
            row = Task(
                user_id=user.id,
                goal_id=goal.id,
                description=item.description,
                estimated_effort_minutes=item.estimated_effort_minutes,
                action_type=item.action_type,
                status=TaskStatus.PENDING,
                payload={"order": item.order},
            )
            self.session.add(row)
            task_rows.append(row)
        await self.session.flush()

        executor = self.registry.get(task_rows[0].action_type)
        start = self.clock.now()
        end = extraction.deadline or start + timedelta(days=7)
        slots = await executor.check_availability(user, start, max(start, end), self.session)
        request = SchedulingRequest(
            user_id=user.id,
            tasks=decomposed,
            deadline=extraction.deadline,
            constraints=extraction.constraints,
            user_timezone=user.timezone,
        )
        schedule = schedule_tasks(slots, request)
        if schedule.failure is None:
            goal.status = GoalStatus.PLANNED

        for action, task in zip(schedule.actions, task_rows):
            action.task_id = task.id
            self.session.add(action)
        await self.session.flush()

        try:
            for action, task in zip(schedule.actions, task_rows):
                action_executor = self.registry.get(task.action_type)
                execution = await action_executor.execute(action, self.session)
                if not execution.success:
                    raise RuntimeError(execution.detail or "Executor failed")
                action.external_ref = execution.external_ref
                action.status = ActionStatus.SCHEDULED
                task.status = TaskStatus.SCHEDULED
            await self.session.commit()
        except Exception:
            for action in schedule.actions:
                if action.external_ref:
                    task = task_rows[schedule.actions.index(action)]
                    try:
                        await self.registry.get(task.action_type).cancel(action, self.session)
                    except Exception:
                        pass
            await self.session.rollback()
            raise

        return PlanOutcome(goal, None, schedule)
