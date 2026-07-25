import re
from loguru import logger
from src.use_cases.travel_goal_service import TravelGoalService


class TelegramCommandHandler:
    """
    Command Handler for Telegram. Parses and dispatches user commands
    to control their Travel Goals, returning human-friendly responses.
    """
    def __init__(self, travel_goal_service: TravelGoalService, conversation_service = None):
        self.travel_goal_service = travel_goal_service
        self.conversation_service = conversation_service

    def handle_command(self, user_id: str, message: str) -> str:
        try:
            msg = message.strip()
            msg_lower = msg.lower()

            # If it's natural chat (not starting with /) and conversation_service is configured
            if not msg.startswith("/") and self.conversation_service:
                from src.utils import mask_chat_id
                logger.info(f"ConversationService called for user {mask_chat_id(user_id)}")
                import asyncio
                import threading
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None

                if loop and loop.is_running():
                    result = []
                    def _run():
                        new_loop = asyncio.new_event_loop()
                        try:
                            res = new_loop.run_until_complete(
                                self.conversation_service.handle_message_async(user_id, msg)
                            )
                            result.append(res)
                        finally:
                            new_loop.close()
                    t = threading.Thread(target=_run)
                    t.start()
                    t.join()
                    return result[0] if result else "Error executing conversational message."
                else:
                    return asyncio.run(self.conversation_service.handle_message_async(user_id, msg))

            # 1. Show Goals Command
            if msg_lower in ("/show", "/show_goals", "show goals", "show"):
                try:
                    goals = self.travel_goal_service.list_goals(user_id)
                    if not goals:
                        return "You have no travel goals configured."

                    lines = []
                    for goal in goals:
                        budget_str = f"₹{goal.budget_inr:,.0f}" if goal.budget_inr > 0 else "None"
                        lines.append(
                            f"Country: {goal.country}\n"
                            f"Window: {goal.start_date.strftime('%Y-%m-%d')} to {goal.end_date.strftime('%Y-%m-%d')}\n"
                            f"Budget: {budget_str}\n"
                            f"Status: {goal.status}\n"
                            f"ID: {goal.id}\n"
                        )
                    return "\n".join(lines).strip()
                except Exception as e:
                    return f"Error listing goals: {e}"

            # 2. Pause Goal Command
            pause_match = re.match(r"^(?:/pause_goal|/pause|pause)\s+(.+)$", msg, re.IGNORECASE)
            if pause_match:
                goal_id = pause_match.group(1).strip()
                try:
                    self.travel_goal_service.pause_goal(user_id, goal_id)
                    return "Goal paused successfully."
                except ValueError as ve:
                    return str(ve)
                except Exception as e:
                    return f"Error pausing goal: {e}"

            # 3. Resume Goal Command
            resume_match = re.match(r"^(?:/resume_goal|/resume|resume)\s+(.+)$", msg, re.IGNORECASE)
            if resume_match:
                goal_id = resume_match.group(1).strip()
                try:
                    self.travel_goal_service.resume_goal(user_id, goal_id)
                    return "Goal resumed successfully."
                except ValueError as ve:
                    return str(ve)
                except Exception as e:
                    return f"Error resuming goal: {e}"

            # 4. Delete Goal Command
            delete_match = re.match(r"^(?:/delete_goal|/delete|delete)\s+(.+)$", msg, re.IGNORECASE)
            if delete_match:
                goal_id = delete_match.group(1).strip()
                try:
                    self.travel_goal_service.delete_goal(user_id, goal_id)
                    return "Goal deleted successfully."
                except ValueError as ve:
                    return str(ve)
                except Exception as e:
                    return f"Error deleting goal: {e}"

            # 5. Add Goal Command
            add_match = re.match(r"^(?:/add_goal|/add|add goal|add)\s+(.+)$", msg, re.IGNORECASE)
            query = add_match.group(1).strip() if add_match else msg

            try:
                goal = self.travel_goal_service.create_goal(user_id, query)
                budget_str = f"₹{goal.budget_inr:,.0f}" if goal.budget_inr > 0 else "None"
                return (
                    f"Goal added successfully:\n"
                    f"Country: {goal.country}\n"
                    f"Window: {goal.start_date.strftime('%Y-%m-%d')} to {goal.end_date.strftime('%Y-%m-%d')}\n"
                    f"Budget: {budget_str}\n"
                    f"Status: {goal.status}\n"
                    f"ID: {goal.id}"
                )
            except ValueError as ve:
                if str(ve) == "Goal already exists.":
                    return "Goal already exists."
                return (
                    f"Sorry, I couldn't understand that. Friendly tip: specify a destination country, "
                    f"date/month/season, and budget (e.g. 'Japan next September under 25000'). Error: {ve}"
                )
            except Exception as e:
                return f"Error creating goal: {e}"
        except Exception as e:
            from src.utils import mask_chat_id
            logger.error(f"Unhandled error in handle_command for user {mask_chat_id(user_id)}: {e}")
            return "⚠️ Sorry, I encountered an unexpected error while processing your request. Please try again later."

    async def handle_command_async(self, user_id: str, message: str) -> str:
        try:
            msg = message.strip()
            if not msg.startswith("/") and self.conversation_service:
                from src.utils import mask_chat_id
                logger.info(f"ConversationService called for user {mask_chat_id(user_id)}")
                return await self.conversation_service.handle_message_async(user_id, msg)
            return self.handle_command(user_id, message)
        except Exception as e:
            from src.utils import mask_chat_id
            logger.error(f"Unhandled error in handle_command_async for user {mask_chat_id(user_id)}: {e}")
            return "⚠️ Sorry, I encountered an unexpected error while processing your request. Please try again later."
