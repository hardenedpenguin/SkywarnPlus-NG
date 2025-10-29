"""
Alert workflow automation system for SkywarnPlus-NG.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Callable, Awaitable, Union
from dataclasses import dataclass
from enum import Enum
import json

from ..core.models import WeatherAlert

logger = logging.getLogger(__name__)


class WorkflowStatus(Enum):
    """Workflow execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ActionType(Enum):
    """Types of workflow actions."""
    NOTIFICATION = "notification"
    SCRIPT_EXECUTION = "script_execution"
    DATABASE_UPDATE = "database_update"
    API_CALL = "api_call"
    CONDITIONAL = "conditional"
    DELAY = "delay"
    ESCALATION = "escalation"


@dataclass
class ResponseAction:
    """A response action in a workflow."""
    
    action_id: str
    action_type: ActionType
    name: str
    description: str
    parameters: Dict[str, Any]
    enabled: bool = True
    timeout_seconds: int = 30
    retry_count: int = 0
    retry_delay_seconds: int = 5
    
    def __post_init__(self):
        if not self.parameters:
            self.parameters = {}


@dataclass
class WorkflowStep:
    """A step in a workflow."""
    
    step_id: str
    name: str
    description: str
    actions: List[ResponseAction]
    conditions: List[Dict[str, Any]]
    parallel: bool = False
    enabled: bool = True
    timeout_seconds: int = 300
    
    def __post_init__(self):
        if not self.actions:
            self.actions = []
        if not self.conditions:
            self.conditions = []


@dataclass
class WorkflowExecution:
    """Execution context for a workflow."""
    
    workflow_id: str
    alert: WeatherAlert
    status: WorkflowStatus
    current_step: Optional[str]
    completed_steps: List[str]
    failed_steps: List[str]
    execution_log: List[Dict[str, Any]]
    started_at: datetime
    completed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if not self.started_at:
            self.started_at = datetime.now(timezone.utc)
        if not self.metadata:
            self.metadata = {}


class AlertWorkflow:
    """Defines a workflow for processing alerts."""
    
    def __init__(
        self,
        workflow_id: str,
        name: str,
        description: str,
        trigger_conditions: List[Dict[str, Any]],
        steps: List[WorkflowStep],
        enabled: bool = True
    ):
        self.workflow_id = workflow_id
        self.name = name
        self.description = description
        self.trigger_conditions = trigger_conditions
        self.steps = steps
        self.enabled = enabled
        self.logger = logging.getLogger(f"{__name__}.{workflow_id}")
    
    def can_trigger(self, alert: WeatherAlert) -> bool:
        """
        Check if this workflow can be triggered by an alert.
        
        Args:
            alert: Weather alert to check
            
        Returns:
            True if workflow can be triggered
        """
        if not self.enabled:
            return False
        
        for condition in self.trigger_conditions:
            if not self._evaluate_condition(alert, condition):
                return False
        
        return True
    
    def _evaluate_condition(self, alert: WeatherAlert, condition: Dict[str, Any]) -> bool:
        """Evaluate a trigger condition."""
        condition_type = condition.get("type", "field_equals")
        
        if condition_type == "field_equals":
            return self._evaluate_field_equals(alert, condition)
        elif condition_type == "field_contains":
            return self._evaluate_field_contains(alert, condition)
        elif condition_type == "severity_equals":
            return self._evaluate_severity_equals(alert, condition)
        elif condition_type == "severity_gte":
            return self._evaluate_severity_gte(alert, condition)
        elif condition_type == "regex_match":
            return self._evaluate_regex_match(alert, condition)
        elif condition_type == "time_range":
            return self._evaluate_time_range(alert, condition)
        else:
            self.logger.warning(f"Unknown condition type: {condition_type}")
            return False
    
    def _evaluate_field_equals(self, alert: WeatherAlert, condition: Dict[str, Any]) -> bool:
        """Evaluate field equals condition."""
        field = condition.get("field", "event")
        expected_value = condition.get("value", "")
        
        actual_value = self._get_field_value(alert, field)
        return str(actual_value) == str(expected_value)
    
    def _evaluate_field_contains(self, alert: WeatherAlert, condition: Dict[str, Any]) -> bool:
        """Evaluate field contains condition."""
        field = condition.get("field", "event")
        expected_value = condition.get("value", "")
        case_sensitive = condition.get("case_sensitive", False)
        
        actual_value = self._get_field_value(alert, field)
        if not actual_value:
            return False
        
        if not case_sensitive:
            actual_value = str(actual_value).lower()
            expected_value = str(expected_value).lower()
        
        return str(expected_value) in str(actual_value)
    
    def _evaluate_severity_equals(self, alert: WeatherAlert, condition: Dict[str, Any]) -> bool:
        """Evaluate severity equals condition."""
        expected_severity = condition.get("severity", "")
        return alert.severity.value == expected_severity
    
    def _evaluate_severity_gte(self, alert: WeatherAlert, condition: Dict[str, Any]) -> bool:
        """Evaluate severity greater than or equal condition."""
        severity_order = {
            "Minor": 1,
            "Moderate": 2,
            "Severe": 3,
            "Extreme": 4
        }
        
        alert_severity = severity_order.get(alert.severity.value, 0)
        expected_severity = severity_order.get(condition.get("severity", "Minor"), 0)
        
        return alert_severity >= expected_severity
    
    def _evaluate_regex_match(self, alert: WeatherAlert, condition: Dict[str, Any]) -> bool:
        """Evaluate regex match condition."""
        import re
        
        field = condition.get("field", "event")
        pattern = condition.get("pattern", "")
        case_sensitive = condition.get("case_sensitive", False)
        
        actual_value = self._get_field_value(alert, field)
        if not actual_value:
            return False
        
        flags = 0 if case_sensitive else re.IGNORECASE
        
        try:
            return bool(re.search(pattern, str(actual_value), flags))
        except re.error as e:
            self.logger.error(f"Regex error in condition: {e}")
            return False
    
    def _evaluate_time_range(self, alert: WeatherAlert, condition: Dict[str, Any]) -> bool:
        """Evaluate time range condition."""
        from datetime import time
        
        start_time = condition.get("start_time", "00:00")
        end_time = condition.get("end_time", "23:59")
        
        alert_time = alert.effective or alert.sent
        if not alert_time:
            return False
        
        # Convert to time object
        alert_time_obj = alert_time.time()
        
        # Parse time strings
        try:
            start = time.fromisoformat(start_time)
            end = time.fromisoformat(end_time)
        except ValueError:
            self.logger.error(f"Invalid time format: {start_time} or {end_time}")
            return False
        
        return start <= alert_time_obj <= end
    
    def _get_field_value(self, alert: WeatherAlert, field: str) -> Any:
        """Get field value from alert."""
        field_mapping = {
            "event": alert.event,
            "headline": alert.headline,
            "description": alert.description,
            "area_desc": alert.area_desc,
            "severity": alert.severity.value,
            "urgency": alert.urgency.value,
            "certainty": alert.certainty.value,
            "status": alert.status.value,
            "category": alert.category.value,
            "sender": alert.sender,
            "sender_name": alert.sender_name
        }
        
        return field_mapping.get(field, "")


class WorkflowEngine:
    """Executes alert workflows."""
    
    def __init__(self):
        self.workflows: Dict[str, AlertWorkflow] = {}
        self.executions: Dict[str, WorkflowExecution] = {}
        self.logger = logging.getLogger(__name__)
    
    def register_workflow(self, workflow: AlertWorkflow) -> None:
        """Register a workflow."""
        self.workflows[workflow.workflow_id] = workflow
        self.logger.info(f"Registered workflow: {workflow.workflow_id}")
    
    def unregister_workflow(self, workflow_id: str) -> None:
        """Unregister a workflow."""
        if workflow_id in self.workflows:
            del self.workflows[workflow_id]
            self.logger.info(f"Unregistered workflow: {workflow_id}")
    
    async def execute_workflows(self, alert: WeatherAlert) -> List[WorkflowExecution]:
        """
        Execute all applicable workflows for an alert.
        
        Args:
            alert: Weather alert to process
            
        Returns:
            List of workflow executions
        """
        self.logger.info(f"Executing workflows for alert {alert.id}")
        
        executions = []
        
        # Find applicable workflows
        applicable_workflows = [
            workflow for workflow in self.workflows.values()
            if workflow.can_trigger(alert)
        ]
        
        if not applicable_workflows:
            self.logger.debug(f"No applicable workflows for alert {alert.id}")
            return executions
        
        # Execute workflows concurrently
        tasks = [
            self._execute_workflow(workflow, alert)
            for workflow in applicable_workflows
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self.logger.error(f"Workflow execution failed: {result}")
                continue
            executions.append(result)
        
        self.logger.info(f"Executed {len(executions)} workflows for alert {alert.id}")
        return executions
    
    async def _execute_workflow(self, workflow: AlertWorkflow, alert: WeatherAlert) -> WorkflowExecution:
        """Execute a single workflow."""
        execution_id = f"{workflow.workflow_id}_{alert.id}_{datetime.now(timezone.utc).timestamp()}"
        
        execution = WorkflowExecution(
            workflow_id=workflow.workflow_id,
            alert=alert,
            status=WorkflowStatus.RUNNING,
            current_step=None,
            completed_steps=[],
            failed_steps=[],
            execution_log=[],
            started_at=datetime.now(timezone.utc)
        )
        
        self.executions[execution_id] = execution
        
        try:
            self.logger.info(f"Executing workflow {workflow.workflow_id} for alert {alert.id}")
            
            for step in workflow.steps:
                if not step.enabled:
                    continue
                
                execution.current_step = step.step_id
                
                try:
                    await self._execute_step(step, alert, execution)
                    execution.completed_steps.append(step.step_id)
                    
                except Exception as e:
                    self.logger.error(f"Step {step.step_id} failed: {e}")
                    execution.failed_steps.append(step.step_id)
                    execution.execution_log.append({
                        "step": step.step_id,
                        "status": "failed",
                        "error": str(e),
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                    
                    # Continue with next step unless step is critical
                    if step.parameters.get("critical", False):
                        execution.status = WorkflowStatus.FAILED
                        break
            
            if execution.status == WorkflowStatus.RUNNING:
                execution.status = WorkflowStatus.COMPLETED
            
        except Exception as e:
            self.logger.error(f"Workflow {workflow.workflow_id} execution failed: {e}")
            execution.status = WorkflowStatus.FAILED
            execution.execution_log.append({
                "workflow": workflow.workflow_id,
                "status": "failed",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        
        finally:
            execution.completed_at = datetime.now(timezone.utc)
            execution.current_step = None
        
        return execution
    
    async def _execute_step(self, step: WorkflowStep, alert: WeatherAlert, execution: WorkflowExecution) -> None:
        """Execute a workflow step."""
        self.logger.debug(f"Executing step {step.step_id}")
        
        # Check step conditions
        for condition in step.conditions:
            if not self._evaluate_step_condition(alert, condition):
                self.logger.debug(f"Step {step.step_id} conditions not met, skipping")
                return
        
        # Execute actions
        if step.parallel:
            # Execute actions in parallel
            tasks = [
                self._execute_action(action, alert, execution)
                for action in step.actions
                if action.enabled
            ]
            await asyncio.gather(*tasks, return_exceptions=True)
        else:
            # Execute actions sequentially
            for action in step.actions:
                if not action.enabled:
                    continue
                
                try:
                    await self._execute_action(action, alert, execution)
                except Exception as e:
                    self.logger.error(f"Action {action.action_id} failed: {e}")
                    if action.parameters.get("critical", False):
                        raise
    
    async def _execute_action(self, action: ResponseAction, alert: WeatherAlert, execution: WorkflowExecution) -> None:
        """Execute a response action."""
        self.logger.debug(f"Executing action {action.action_id}")
        
        try:
            if action.action_type == ActionType.NOTIFICATION:
                await self._execute_notification_action(action, alert, execution)
            elif action.action_type == ActionType.SCRIPT_EXECUTION:
                await self._execute_script_action(action, alert, execution)
            elif action.action_type == ActionType.DATABASE_UPDATE:
                await self._execute_database_action(action, alert, execution)
            elif action.action_type == ActionType.API_CALL:
                await self._execute_api_action(action, alert, execution)
            elif action.action_type == ActionType.CONDITIONAL:
                await self._execute_conditional_action(action, alert, execution)
            elif action.action_type == ActionType.DELAY:
                await self._execute_delay_action(action, alert, execution)
            elif action.action_type == ActionType.ESCALATION:
                await self._execute_escalation_action(action, alert, execution)
            else:
                self.logger.warning(f"Unknown action type: {action.action_type}")
            
            execution.execution_log.append({
                "action": action.action_id,
                "status": "completed",
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
        except Exception as e:
            self.logger.error(f"Action {action.action_id} failed: {e}")
            execution.execution_log.append({
                "action": action.action_id,
                "status": "failed",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            raise
    
    async def _execute_notification_action(self, action: ResponseAction, alert: WeatherAlert, execution: WorkflowExecution) -> None:
        """Execute notification action."""
        # This would integrate with notification systems
        self.logger.info(f"Notification action: {action.name}")
        # Placeholder implementation
    
    async def _execute_script_action(self, action: ResponseAction, alert: WeatherAlert, execution: WorkflowExecution) -> None:
        """Execute script action."""
        # This would integrate with the script execution system
        self.logger.info(f"Script action: {action.name}")
        # Placeholder implementation
    
    async def _execute_database_action(self, action: ResponseAction, alert: WeatherAlert, execution: WorkflowExecution) -> None:
        """Execute database action."""
        # This would integrate with the database system
        self.logger.info(f"Database action: {action.name}")
        # Placeholder implementation
    
    async def _execute_api_action(self, action: ResponseAction, alert: WeatherAlert, execution: WorkflowExecution) -> None:
        """Execute API call action."""
        # This would make HTTP API calls
        self.logger.info(f"API action: {action.name}")
        # Placeholder implementation
    
    async def _execute_conditional_action(self, action: ResponseAction, alert: WeatherAlert, execution: WorkflowExecution) -> None:
        """Execute conditional action."""
        # This would evaluate conditions and execute sub-actions
        self.logger.info(f"Conditional action: {action.name}")
        # Placeholder implementation
    
    async def _execute_delay_action(self, action: ResponseAction, alert: WeatherAlert, execution: WorkflowExecution) -> None:
        """Execute delay action."""
        delay_seconds = action.parameters.get("delay_seconds", 0)
        if delay_seconds > 0:
            await asyncio.sleep(delay_seconds)
    
    async def _execute_escalation_action(self, action: ResponseAction, alert: WeatherAlert, execution: WorkflowExecution) -> None:
        """Execute escalation action."""
        # This would escalate the alert to higher priority workflows
        self.logger.info(f"Escalation action: {action.name}")
        # Placeholder implementation
    
    def _evaluate_step_condition(self, alert: WeatherAlert, condition: Dict[str, Any]) -> bool:
        """Evaluate a step condition."""
        # Similar to workflow trigger conditions
        condition_type = condition.get("type", "field_equals")
        
        if condition_type == "field_equals":
            field = condition.get("field", "event")
            expected_value = condition.get("value", "")
            actual_value = self._get_field_value(alert, field)
            return str(actual_value) == str(expected_value)
        
        # Add more condition types as needed
        return True
    
    def _get_field_value(self, alert: WeatherAlert, field: str) -> Any:
        """Get field value from alert."""
        field_mapping = {
            "event": alert.event,
            "headline": alert.headline,
            "description": alert.description,
            "area_desc": alert.area_desc,
            "severity": alert.severity.value,
            "urgency": alert.urgency.value,
            "certainty": alert.certainty.value,
            "status": alert.status.value,
            "category": alert.category.value,
            "sender": alert.sender,
            "sender_name": alert.sender_name
        }
        
        return field_mapping.get(field, "")
    
    def get_execution_status(self, execution_id: str) -> Optional[WorkflowExecution]:
        """Get execution status by ID."""
        return self.executions.get(execution_id)
    
    def get_workflow_executions(self, workflow_id: Optional[str] = None) -> List[WorkflowExecution]:
        """Get workflow executions."""
        if workflow_id:
            return [
                execution for execution in self.executions.values()
                if execution.workflow_id == workflow_id
            ]
        return list(self.executions.values())
    
    def cleanup_old_executions(self, max_age_hours: int = 24) -> int:
        """Clean up old executions."""
        cutoff_time = datetime.now(timezone.utc).timestamp() - (max_age_hours * 3600)
        
        old_executions = [
            exec_id for exec_id, execution in self.executions.items()
            if execution.started_at.timestamp() < cutoff_time
        ]
        
        for exec_id in old_executions:
            del self.executions[exec_id]
        
        self.logger.info(f"Cleaned up {len(old_executions)} old executions")
        return len(old_executions)
