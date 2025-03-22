"""
Transfer logging module for Android Media Transfer Tool.
Handles logging of file transfer operations.
"""

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

@dataclass
class TransferLogEntry:
    """Single transfer operation log entry"""
    timestamp: str
    source_dir: str
    destination_dir: str
    successful_files: List[str]
    failed_files: List[str]
    failed_paths: List[str]
    total_size: int
    duration: float
    delete_source: bool

class TransferLogger:
    """Manages transfer operation logging"""

    def __init__(self, log_dir: str = None):
        """
        Initialize transfer logger
        
        Args:
            log_dir: Directory to store log files (default: ~/.config/amtt/logs)
        """
        if log_dir is None:
            config_dir = os.path.expanduser("~/.config/amtt")
            log_dir = os.path.join(config_dir, "logs")
        
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
    def _get_log_file(self) -> Path:
        """Get the log file path for the current date"""
        today = datetime.now().strftime("%Y-%m-%d")
        return self.log_dir / f"transfer_log_{today}.json"
        
    def _load_logs(self) -> List[dict]:
        """Load existing logs for the current day"""
        log_file = self._get_log_file()
        if log_file.exists():
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return []
        return []
        
    def _save_logs(self, logs: List[dict]):
        """Save logs to file"""
        log_file = self._get_log_file()
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(logs, f, indent=2, ensure_ascii=False)
            
    def add_entry(self, entry: TransferLogEntry):
        """Add a new transfer log entry"""
        # Load existing logs
        logs = self._load_logs()
        
        # Convert entry to dict and add to logs
        entry_dict = asdict(entry)
        logs.append(entry_dict)
        
        # Save updated logs
        self._save_logs(logs)
        
    def get_entries(self, date: Optional[str] = None) -> List[TransferLogEntry]:
        """
        Get transfer log entries for a specific date
        
        Args:
            date: Date string in YYYY-MM-DD format (default: today)
            
        Returns:
            List of TransferLogEntry objects
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
            
        log_file = self.log_dir / f"transfer_log_{date}.json"
        if not log_file.exists():
            return []
            
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                logs = json.load(f)
                return [TransferLogEntry(**entry) for entry in logs]
        except (json.JSONDecodeError, KeyError):
            return []
            
    def get_log_dates(self) -> List[str]:
        """Get list of dates that have transfer logs"""
        log_files = self.log_dir.glob("transfer_log_*.json")
        dates = []
        for log_file in log_files:
            try:
                date = log_file.stem.split("_")[-1]
                dates.append(date)
            except IndexError:
                continue
        return sorted(dates) 