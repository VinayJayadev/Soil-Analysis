"""
Comprehensive logging system for the geospatial soil analysis pipeline.
Handles multiple log files, different log levels, and performance tracking.
"""

import logging
import logging.handlers
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
import time
import json


class PipelineLogger:
    """
    Main logging class for the pipeline with multiple log files and performance tracking.
    """
    
    def __init__(self, run_id: str, log_directory: str = "logs", 
                 console_level: str = "INFO", file_level: str = "DEBUG", db_manager=None):
        """
        Initialize the pipeline logger.
        
        Args:
            run_id: Unique identifier for this pipeline run
            log_directory: Directory to store log files
            console_level: Log level for console output
            file_level: Log level for file output
            db_manager: Optional DatabaseManager instance for DB logging
        """
        self.run_id = run_id
        self.log_directory = Path(log_directory)
        self.start_time = datetime.now()
        self.stage_start_times = {}
        self.db_manager = db_manager
        
        # Create log directory if it doesn't exist
        self.log_directory.mkdir(parents=True, exist_ok=True)
        
        # Setup loggers
        self.setup_loggers(console_level, file_level)
        
        # Log pipeline start
        self.logger.info(f"Pipeline started - Run ID: {run_id}")
        self.logger.info(f"Start time: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        if self.db_manager:
            self.db_manager.log_to_pipeline_logs(
                self.run_id, "pipeline_start", "INFO", f"Pipeline started - Run ID: {run_id}")
            self.db_manager.log_to_pipeline_logs(
                self.run_id, "pipeline_start", "INFO", f"Start time: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    def setup_loggers(self, console_level: str, file_level: str):
        """Setup all loggers with appropriate handlers and formatters."""
        
        # Main pipeline logger
        self.logger = self._create_logger(
            "pipeline",
            f"pipeline_{self.run_id}.log",
            console_level,
            file_level
        )
        
        # Database logger
        self.db_logger = self._create_logger(
            "database",
            f"database_{self.run_id}.log",
            console_level,
            file_level
        )
        
        # API logger
        self.api_logger = self._create_logger(
            "api",
            f"api_{self.run_id}.log",
            console_level,
            file_level
        )
        
        # Error logger (only errors)
        self.error_logger = self._create_logger(
            "errors",
            f"errors_{self.run_id}.log",
            "ERROR",
            "ERROR"
        )
        
        # Performance logger
        self.perf_logger = self._create_logger(
            "performance",
            f"performance_{self.run_id}.log",
            "INFO",
            "DEBUG"
        )
    
    def _create_logger(self, name: str, filename: str, console_level: str, file_level: str):
        """Create a logger with console and file handlers."""
        
        logger = logging.getLogger(name)
        logger.setLevel(logging.DEBUG)
        
        # Clear existing handlers
        logger.handlers.clear()
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, console_level.upper()))
        console_formatter = logging.Formatter('%(levelname)s - %(message)s')
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
        
        # File handler
        file_path = self.log_directory / filename
        file_handler = logging.FileHandler(file_path, encoding='utf-8')
        file_handler.setLevel(getattr(logging, file_level.upper()))
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        
        return logger
    
    def log_stage_start(self, stage_name: str, description: str = ""):
        """Log the start of a pipeline stage."""
        self.stage_start_times[stage_name] = time.time()
        message = f"Stage: {stage_name}"
        if description:
            message += f" - {description}"
        self.logger.info(message)
        self.logger.debug(f"Stage '{stage_name}' started at {datetime.now().strftime('%H:%M:%S')}")
        if self.db_manager:
            self.db_manager.log_to_pipeline_logs(
                self.run_id, stage_name, "INFO", message)
    
    def log_stage_complete(self, stage_name: str, metrics: Optional[Dict[str, Any]] = None):
        """Log the completion of a pipeline stage with performance metrics."""
        if stage_name in self.stage_start_times:
            duration = time.time() - self.stage_start_times[stage_name]
            duration_str = f"{duration:.1f}s"
            
            message = f"Stage completed: {stage_name} ({duration_str})"
            if metrics:
                metric_strs = []
                for key, value in metrics.items():
                    if isinstance(value, (int, float)):
                        metric_strs.append(f"{key}: {value:,}" if isinstance(value, int) else f"{key}: {value}")
                    else:
                        metric_strs.append(f"{key}: {value}")
                message += f" - {', '.join(metric_strs)}"
            
            self.logger.info(message)
            self.log_performance(stage_name, duration * 1000, metrics)
            if self.db_manager:
                self.db_manager.log_to_pipeline_logs(
                    self.run_id, stage_name, "INFO", message, duration_ms=int(duration*1000),
                    record_count=metrics.get("records") if metrics else None)
            
            # Remove from tracking
            del self.stage_start_times[stage_name]
        else:
            self.logger.warning(f"Stage '{stage_name}' completed but start time not found")
    
    def log_data_loaded(self, table_name: str, record_count: int, duration: float = None):
        """Log data loading statistics."""
        message = f"Loaded {record_count:,} records into {table_name}"
        if duration:
            message += f" in {duration:.2f}s"
        self.logger.info(message)
        
        if duration:
            self.log_performance(f"data_load_{table_name}", duration * 1000, {"records": record_count})
        if self.db_manager:
            self.db_manager.log_to_pipeline_logs(
                self.run_id, f"data_load_{table_name}", "INFO", message, duration_ms=int(duration*1000) if duration else None, record_count=record_count)
    
    def log_error(self, error: Exception, context: str = "", stage: str = ""):
        """Log errors with full context."""
        error_message = f"Error in {stage}: {str(error)}" if stage else f"Error: {str(error)}"
        if context:
            error_message += f" - Context: {context}"
        
        self.logger.error(error_message)
        self.error_logger.error(error_message)
        
        # Log full error details to error file
        error_details = {
            "timestamp": datetime.now().isoformat(),
            "run_id": self.run_id,
            "stage": stage,
            "context": context,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": self._get_traceback()
        }
        self.error_logger.error(f"Error details: {json.dumps(error_details, indent=2)}")
        if self.db_manager:
            self.db_manager.log_to_pipeline_logs(
                self.run_id, stage or "error", "ERROR", error_message, error_details=json.dumps(error_details))
    
    def log_warning(self, message: str, context: str = ""):
        """Log warnings."""
        full_message = message
        if context:
            full_message += f" - Context: {context}"
        self.logger.warning(full_message)
        if self.db_manager:
            self.db_manager.log_to_pipeline_logs(
                self.run_id, "warning", "WARNING", full_message)
    
    def log_performance(self, operation: str, duration_ms: float, details: Optional[Dict[str, Any]] = None):
        """Log performance metrics."""
        message = f"PERFORMANCE - {operation}: {duration_ms:.2f}ms"
        if details:
            detail_strs = []
            for key, value in details.items():
                if isinstance(value, (int, float)):
                    detail_strs.append(f"{key}: {value:,}" if isinstance(value, int) else f"{key}: {value}")
                else:
                    detail_strs.append(f"{key}: {value}")
            message += f" - {', '.join(detail_strs)}"
        
        self.perf_logger.info(message)
        
        # Log to main logger if performance is significant
        if duration_ms > 1000:  # More than 1 second
            self.logger.info(message)
        if self.db_manager:
            self.db_manager.log_to_pipeline_logs(
                self.run_id, operation, "INFO", message, duration_ms=int(duration_ms))
    
    def log_database_operation(self, operation: str, table: str = "", record_count: int = None, duration: float = None):
        """Log database operations."""
        message = f"Database {operation}"
        if table:
            message += f" on {table}"
        if record_count is not None:
            message += f" - {record_count:,} records"
        if duration:
            message += f" in {duration:.2f}s"
        
        self.db_logger.info(message)
        
        if duration:
            self.log_performance(f"db_{operation}_{table}", duration * 1000, {"records": record_count})
        if self.db_manager:
            self.db_manager.log_to_pipeline_logs(
                self.run_id, f"db_{operation}_{table}", "INFO", message, duration_ms=int(duration*1000) if duration else None, record_count=record_count)
    
    def log_api_request(self, endpoint: str, method: str = "GET", duration: float = None, status_code: int = None):
        """Log API requests."""
        message = f"API {method} {endpoint}"
        if status_code:
            message += f" - Status: {status_code}"
        if duration:
            message += f" in {duration:.2f}s"
        
        self.api_logger.info(message)
        
        if duration:
            self.log_performance(f"api_{method.lower()}_{endpoint}", duration * 1000, {"status": status_code})
        if self.db_manager:
            self.db_manager.log_to_pipeline_logs(
                self.run_id, f"api_{method.lower()}_{endpoint}", "INFO", message, duration_ms=int(duration*1000) if duration else None)
    
    def log_pipeline_complete(self, total_records: int = None, total_countries: int = None):
        """Log pipeline completion with summary statistics."""
        total_duration = time.time() - self.stage_start_times.get("pipeline_start", time.time())
        
        self.logger.info("Pipeline completed successfully")
        self.logger.info(f"Total execution time: {total_duration:.1f}s")
        
        if total_records:
            self.logger.info(f"Records processed: {total_records:,}")
        if total_countries:
            self.logger.info(f"Countries analyzed: {total_countries}")
        
        # Log final performance summary
        self.log_performance("pipeline_total", total_duration * 1000, {
            "records": total_records,
            "countries": total_countries
        })
        if self.db_manager:
            self.db_manager.log_to_pipeline_logs(
                self.run_id, "pipeline_complete", "INFO", "Pipeline completed successfully", duration_ms=int(total_duration*1000), record_count=total_records)
    
    def _get_traceback(self) -> str:
        """Get current traceback as string."""
        import traceback
        return traceback.format_exc()
    
    def get_log_files(self) -> Dict[str, str]:
        """Get paths to all log files for this run."""
        return {
            "pipeline": str(self.log_directory / f"pipeline_{self.run_id}.log"),
            "database": str(self.log_directory / f"database_{self.run_id}.log"),
            "api": str(self.log_directory / f"api_{self.run_id}.log"),
            "errors": str(self.log_directory / f"errors_{self.run_id}.log"),
            "performance": str(self.log_directory / f"performance_{self.run_id}.log")
        }


class DatabaseLogger:
    """Specialized logger for database operations."""
    
    def __init__(self, pipeline_logger: PipelineLogger):
        self.pipeline_logger = pipeline_logger
    
    def log_query(self, query: str, params: tuple = None, duration: float = None):
        """Log database queries with performance."""
        # Truncate long queries for readability
        query_preview = query[:100] + "..." if len(query) > 100 else query
        
        message = f"Query: {query_preview}"
        if params:
            message += f" - Params: {params}"
        if duration:
            message += f" - Duration: {duration:.3f}s"
        
        self.pipeline_logger.db_logger.debug(message)
        
        if duration and duration > 0.1:  # Log slow queries
            self.pipeline_logger.log_performance("db_query", duration * 1000, {"query_preview": query_preview})
    
    def log_transaction(self, operation: str, table: str, record_count: int, duration: float = None):
        """Log database transactions."""
        self.pipeline_logger.log_database_operation(operation, table, record_count, duration)
    
    def log_connection(self, status: str, details: str = ""):
        """Log database connection events."""
        message = f"Database connection: {status}"
        if details:
            message += f" - {details}"
        self.pipeline_logger.db_logger.info(message)


class APILogger:
    """Specialized logger for API operations."""
    
    def __init__(self, pipeline_logger: PipelineLogger):
        self.pipeline_logger = pipeline_logger
    
    def log_request(self, endpoint: str, method: str = "GET", params: dict = None, 
                   response_time: float = None, status_code: int = None):
        """Log API requests and responses."""
        self.pipeline_logger.log_api_request(endpoint, method, response_time, status_code)
        
        if params:
            self.pipeline_logger.api_logger.debug(f"Request params: {params}")
    
    def log_error(self, endpoint: str, error: Exception, retry_count: int = 0):
        """Log API errors and retries."""
        message = f"API error for {endpoint}: {str(error)}"
        if retry_count > 0:
            message += f" (Retry {retry_count})"
        
        self.pipeline_logger.api_logger.error(message)
        self.pipeline_logger.log_error(error, f"API endpoint: {endpoint}", "api")


def create_run_id() -> str:
    """Create a unique run ID based on current timestamp."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def setup_logging(run_id: str = None, log_directory: str = "logs", db_manager=None) -> PipelineLogger:
    """Convenience function to setup logging for the pipeline."""
    if run_id is None:
        run_id = create_run_id()
    return PipelineLogger(run_id, log_directory, db_manager=db_manager)


if __name__ == "__main__":
    # Test the logging system
    logger = setup_logging("test_run")
    
    logger.log_stage_start("Test Stage", "Testing logging functionality")
    logger.log_data_loaded("test_table", 1000, 2.5)
    logger.log_performance("test_operation", 1500, {"records": 1000})
    logger.log_stage_complete("Test Stage", {"records": 1000, "duration": 2.5})
    
    try:
        raise ValueError("Test error")
    except Exception as e:
        logger.log_error(e, "Test context", "Test Stage")
    
    logger.log_pipeline_complete(1000, 5)
    
    print("Logging test completed. Check the logs/ directory for output files.") 