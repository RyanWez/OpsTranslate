import asyncio
import gzip
import json
from pathlib import Path
import pytest

from scripts.backup_db import create_backup, list_backups, prune_backups, _compute_sha256


@pytest.mark.asyncio
async def test_backup_create_list_and_prune(tmp_path: Path):
    backup_file = await create_backup(dest_dir=tmp_path)
    assert backup_file.exists()
    assert backup_file.name.endswith(".sql.gz")
    
    # Check that it's a valid gzip file
    with gzip.open(backup_file, "rb") as f:
        content = f.read()
        assert len(content) > 0
        data = json.loads(content.decode("utf-8"))
        assert isinstance(data, dict)
        
    # Check list_backups
    backups = list_backups(dest_dir=tmp_path)
    assert len(backups) == 1
    assert backups[0]["filename"] == backup_file.name
    assert backups[0]["sha256"] == _compute_sha256(backup_file)
    
    # Prune with keep_days=1 should keep current backup
    pruned = prune_backups(keep_days=1, dest_dir=tmp_path)
    assert pruned == 0
    assert backup_file.exists()
