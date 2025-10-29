"""
Core alert processing pipeline for SkywarnPlus-NG.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Callable, Awaitable
from dataclasses import dataclass
from enum import Enum

from ..core.models import WeatherAlert

logger = logging.getLogger(__name__)


class ProcessingStage(Enum):
    """Alert processing stages."""
    RECEIVED = "received"
    FILTERED = "filtered"
    DEDUPLICATED = "deduplicated"
    PRIORITIZED = "prioritized"
    VALIDATED = "validated"
    WORKFLOW_EXECUTED = "workflow_executed"
    COMPLETED = "completed"


class ProcessingError(Exception):
    """Alert processing error."""

    pass


@dataclass
class ProcessingContext:
    """Context for alert processing."""
    
    alert: WeatherAlert
    stage: ProcessingStage
    metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc)
        if not self.updated_at:
            self.updated_at = datetime.now(timezone.utc)


@dataclass
class ProcessingResult:
    """Result of alert processing."""
    
    alert: WeatherAlert
    processed: bool
    stage: ProcessingStage
    actions_taken: List[str]
    metadata: Dict[str, Any]
    processing_time_ms: float
    errors: List[str]
    
    def add_action(self, action: str) -> None:
        """Add an action taken during processing."""
        self.actions_taken.append(action)
    
    def add_error(self, error: str) -> None:
        """Add an error that occurred during processing."""
        self.errors.append(error)


class AlertProcessor:
    """Base class for alert processors."""
    
    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(f"{__name__}.{name}")
    
    async def process(self, context: ProcessingContext) -> ProcessingContext:
        """
        Process an alert context.
        
        Args:
            context: Processing context
            
        Returns:
            Updated processing context
        """
        raise NotImplementedError
    
    def can_process(self, context: ProcessingContext) -> bool:
        """
        Check if this processor can handle the given context.
        
        Args:
            context: Processing context
            
        Returns:
            True if this processor can handle the context
        """
        return True


class AlertProcessingPipeline:
    """Main alert processing pipeline."""
    
    def __init__(self):
        self.processors: List[AlertProcessor] = []
        self.stage_processors: Dict[ProcessingStage, List[AlertProcessor]] = {}
        self.logger = logging.getLogger(__name__)
        self._processing_stats = {
            "total_processed": 0,
            "successful": 0,
            "failed": 0,
            "stage_counts": {stage.value: 0 for stage in ProcessingStage}
        }
    
    def add_processor(self, processor: AlertProcessor, stage: ProcessingStage) -> None:
        """
        Add a processor to the pipeline.
        
        Args:
            processor: Alert processor
            stage: Processing stage
        """
        self.processors.append(processor)
        
        if stage not in self.stage_processors:
            self.stage_processors[stage] = []
        self.stage_processors[stage].append(processor)
        
        self.logger.info(f"Added processor '{processor.name}' to stage '{stage.value}'")
    
    def remove_processor(self, processor_name: str) -> None:
        """
        Remove a processor from the pipeline.
        
        Args:
            processor_name: Name of processor to remove
        """
        self.processors = [p for p in self.processors if p.name != processor_name]
        
        for stage, processors in self.stage_processors.items():
            self.stage_processors[stage] = [p for p in processors if p.name != processor_name]
        
        self.logger.info(f"Removed processor '{processor_name}' from pipeline")
    
    async def process_alert(self, alert: WeatherAlert, initial_metadata: Optional[Dict[str, Any]] = None) -> ProcessingResult:
        """
        Process a single alert through the pipeline.
        
        Args:
            alert: Weather alert to process
            initial_metadata: Initial processing metadata
            
        Returns:
            Processing result
        """
        start_time = datetime.now(timezone.utc)
        
        # Create initial context
        context = ProcessingContext(
            alert=alert,
            stage=ProcessingStage.RECEIVED,
            metadata=initial_metadata or {},
            created_at=start_time,
            updated_at=start_time
        )
        
        result = ProcessingResult(
            alert=alert,
            processed=False,
            stage=ProcessingStage.RECEIVED,
            actions_taken=[],
            metadata=context.metadata.copy(),
            processing_time_ms=0.0,
            errors=[]
        )
        
        try:
            # Process through each stage
            for stage in ProcessingStage:
                if stage == ProcessingStage.RECEIVED:
                    continue  # Skip initial stage
                
                context.stage = stage
                context.updated_at = datetime.now(timezone.utc)
                
                # Get processors for this stage
                stage_processors = self.stage_processors.get(stage, [])
                
                if not stage_processors:
                    self.logger.debug(f"No processors for stage '{stage.value}', skipping")
                    continue
                
                # Process with each processor in the stage
                for processor in stage_processors:
                    if not processor.can_process(context):
                        self.logger.debug(f"Processor '{processor.name}' cannot process context, skipping")
                        continue
                    
                    try:
                        self.logger.debug(f"Processing alert {alert.id} with '{processor.name}' in stage '{stage.value}'")
                        context = await processor.process(context)
                        result.add_action(f"{processor.name}:{stage.value}")
                        
                    except Exception as e:
                        error_msg = f"Processor '{processor.name}' failed: {str(e)}"
                        self.logger.error(error_msg, exc_info=True)
                        result.add_error(error_msg)
                        
                        # Continue processing with other processors
                        continue
                
                # Update stage counts
                self._processing_stats["stage_counts"][stage.value] += 1
            
            # Mark as completed
            context.stage = ProcessingStage.COMPLETED
            result.stage = ProcessingStage.COMPLETED
            result.processed = True
            
            # Update statistics
            self._processing_stats["total_processed"] += 1
            self._processing_stats["successful"] += 1
            
        except Exception as e:
            error_msg = f"Pipeline processing failed: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            result.add_error(error_msg)
            result.processed = False
            
            # Update statistics
            self._processing_stats["total_processed"] += 1
            self._processing_stats["failed"] += 1
        
        finally:
            # Calculate processing time
            end_time = datetime.now(timezone.utc)
            result.processing_time_ms = (end_time - start_time).total_seconds() * 1000
            
            self.logger.info(
                f"Alert {alert.id} processing completed in {result.processing_time_ms:.2f}ms "
                f"(stage: {result.stage.value}, processed: {result.processed})"
            )
        
        return result
    
    async def process_alerts(self, alerts: List[WeatherAlert], max_concurrent: int = 10) -> List[ProcessingResult]:
        """
        Process multiple alerts through the pipeline.
        
        Args:
            alerts: List of weather alerts to process
            max_concurrent: Maximum number of concurrent processing tasks
            
        Returns:
            List of processing results
        """
        self.logger.info(f"Processing {len(alerts)} alerts with max concurrency of {max_concurrent}")
        
        # Create semaphore to limit concurrent processing
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def process_with_semaphore(alert: WeatherAlert) -> ProcessingResult:
            async with semaphore:
                return await self.process_alert(alert)
        
        # Process alerts concurrently
        tasks = [process_with_semaphore(alert) for alert in alerts]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle any exceptions
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self.logger.error(f"Alert {alerts[i].id} processing failed: {result}")
                # Create error result
                error_result = ProcessingResult(
                    alert=alerts[i],
                    processed=False,
                    stage=ProcessingStage.RECEIVED,
                    actions_taken=[],
                    metadata={},
                    processing_time_ms=0.0,
                    errors=[str(result)]
                )
                processed_results.append(error_result)
            else:
                processed_results.append(result)
        
        self.logger.info(f"Completed processing {len(alerts)} alerts")
        return processed_results
    
    def get_processing_stats(self) -> Dict[str, Any]:
        """Get processing statistics."""
        stats = self._processing_stats.copy()
        
        # Calculate success rate
        if stats["total_processed"] > 0:
            stats["success_rate"] = stats["successful"] / stats["total_processed"]
        else:
            stats["success_rate"] = 0.0
        
        return stats
    
    def reset_stats(self) -> None:
        """Reset processing statistics."""
        self._processing_stats = {
            "total_processed": 0,
            "successful": 0,
            "failed": 0,
            "stage_counts": {stage.value: 0 for stage in ProcessingStage}
        }
        self.logger.info("Processing statistics reset")
