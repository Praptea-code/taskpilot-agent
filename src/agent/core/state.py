from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent.models import ActionStatus, Goal, GoalStatus, ScheduledAction, Task, TaskStatus


async def finish_goal_if_done(session: AsyncSession, goal_id: int) -> None:
    result = await session.execute(select(Task).where(Task.goal_id == goal_id))
    tasks = list(result.scalars().all())
    if tasks and all(task.status == TaskStatus.DONE for task in tasks):
        goal = await session.get(Goal, goal_id)
        if goal is not None:
            goal.status = GoalStatus.DONE


async def mark_action_done(session: AsyncSession, action: ScheduledAction) -> None:
    task = await session.get(Task, action.task_id)
    if task is None:
        return
    action.status = ActionStatus.DONE
    task.status = TaskStatus.DONE
    await finish_goal_if_done(session, task.goal_id)
