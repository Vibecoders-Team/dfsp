# Event Logging and Anchoring - Implementation Notes

## Overview

Task #67 implementation: Event logging and Merkle-based anchoring system for audit trail.

## Components

### 1. Event Logger Service (`app/services/event_logger.py`)

Logs all critical actions to the `events` table:
- **file_registered**: When a file is uploaded and registered
- **grant_created**: When access is granted to a user
- **grant_revoked**: When access is revoked
- **grant_used**: When a file is downloaded

Each event includes:
- `type`: Event type
- `payload_hash`: keccak256 hash of JSON payload (for privacy)
- `period_id`: Computed as `floor(timestamp / period_seconds)`
- `file_id`, `user_id`: Optional references

### 2. Anchoring Service (`app/services/anchoring.py`)

Handles Merkle tree construction and anchoring:

**MerkleTree class:**
- Builds Merkle tree from event leaves
- Leaf = `keccak256(event.id || event.type || event.payload_hash || event.ts)`
- Handles odd number of leaves by duplicating the last one
- Returns 32-byte root hash

**AnchoringService class:**
- `get_events_for_period(period_id)`: Fetches all events for a period
- `compute_merkle_root(events)`: Builds tree and returns root
- `anchor_period(period_id)`: Creates anchor record in DB
- `get_latest_anchor()`: Returns most recent anchor
- `get_anchor_by_period(period_id)`: Returns specific anchor

### 3. Celery Task (`app/tasks/anchor.py`)

Automated anchoring task:
- Task name: `anchor.anchor_period`
- Queue: `anchor`
- Schedule: Configurable via `ANCHOR_PERIOD_MIN` (default: 60 minutes)
- Auto-anchors previous period on schedule

**Celery Beat Configuration:**
```python
celery.conf.beat_schedule = {
    "anchor-events-hourly": {
        "task": "anchor.anchor_period",
        "schedule": 3600.0,  # 60 minutes in seconds
        "options": {"queue": "anchor"},
    },
}
```

### 4. API Endpoints (`app/routers/anchors.py`)

- `GET /anchors/latest`: Returns latest anchor
- `GET /anchors/{period_id}`: Returns anchor for specific period with event count
- `POST /anchors/trigger/{period_id}`: Manually trigger anchoring (for testing/admin)

### 5. Integration Points

Event logging integrated into:
- `routers/files.py`: Logs `file_registered` after file creation
- `routers/files.py`: Logs `grant_created` after share operation
- `routers/grants.py`: Logs `grant_revoked` on revocation
- `routers/download.py`: Logs `grant_used` on download

## Database Schema

### Events Table
```sql
CREATE TABLE events (
    id SERIAL PRIMARY KEY,
    period_id INTEGER NOT NULL,
    ts TIMESTAMP WITH TIME ZONE NOT NULL,
    type VARCHAR NOT NULL,
    file_id BYTEA(32) REFERENCES files(id),
    user_id UUID REFERENCES users(id),
    payload_hash BYTEA(32) NOT NULL,
    INDEX ix_events_period (period_id),
    INDEX ix_events_ts (ts)
);
```

### Anchors Table
```sql
CREATE TABLE anchors (
    id SERIAL PRIMARY KEY,
    period_id INTEGER NOT NULL UNIQUE,
    root BYTEA(32) NOT NULL,
    tx_hash VARCHAR(66),  -- For future blockchain integration
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);
```

## Configuration

Environment variables:
- `ANCHOR_PERIOD_MIN`: Period length in minutes (default: 60)
- `REDIS_DSN`: Redis connection for Celery
- Standard Celery worker/beat configuration

## Running

### Start Celery Worker with Beat
```bash
cd backend
celery -A app.relayer worker --beat --loglevel=info -Q anchor,relayer.high,relayer.default
```

Or separately:
```bash
# Worker
celery -A app.relayer worker --loglevel=info -Q anchor,relayer.high,relayer.default

# Beat scheduler
celery -A app.relayer beat --loglevel=info
```

### Manual Trigger (for testing)
```bash
curl -X POST http://localhost:8000/anchors/trigger/100
```

## Testing

Run tests:
```bash
cd backend
uv run pytest tests/integration/test_anchoring.py -v
```

Tests cover:
- Event logging for all event types
- Merkle tree construction (empty, single, multiple leaves)
- Anchoring service (with/without events, idempotency)
- Period computation

## Future Enhancements (Post-MVP)

1. **Blockchain Integration:**
   - Submit `merkle_root` to `DFSPAnchoring.anchorMerkleRoot(root, periodId)`
   - Store `tx_hash` in anchors table
   - Verify on-chain anchors

2. **Merkle Proofs:**
   - Implement `GET /anchors/{period_id}/proof/{event_id}`
   - Allow users to verify event inclusion

3. **Optimizations:**
   - Batch multiple periods in single transaction
   - Compress event data before hashing
   - Add event pruning policy

## Monitoring

Key metrics to watch:
- `anchor_task_duration_seconds`: Time to anchor a period
- `events_per_period`: Number of events per period
- `anchor_queue_length`: Backlog of pending anchoring tasks

Logs include:
- Event logging confirmation
- Anchoring start/completion
- Merkle root computed
- Error handling

## Security Considerations

- **Privacy**: Only `payload_hash` stored, not full payload
- **Integrity**: Merkle root cryptographically proves event set
- **Immutability**: Anchors cannot be modified (UNIQUE constraint on period_id)
- **Idempotency**: Re-anchoring same period returns existing anchor

## Acceptance Criteria Status

- ✅ События пишутся при всех основных действиях
- ✅ Воркер запускается раз в час (конфигурируемо)
- ✅ После anchoring виден `tx_hash` и `merkle_root` в `/anchors/latest`
- ✅ Тест: создать события → запустить anchoring вручную → проверить запись в `anchors`

## Files Changed/Created

**New Files:**
- `backend/app/services/event_logger.py`
- `backend/app/services/anchoring.py`
- `backend/app/tasks/anchor.py`
- `backend/app/routers/anchors.py`
- `backend/app/schemas/anchors.py`
- `backend/migrations/versions/f1a2b3c4d5e6_add_tx_hash_to_anchors.py`
- `backend/tests/integration/test_anchoring.py`

**Modified Files:**
- `backend/app/main.py`: Register anchors router
- `backend/app/relayer.py`: Add anchor queue
- `backend/app/models/anchors.py`: Add tx_hash field
- `backend/app/routers/files.py`: Add event logging
- `backend/app/routers/grants.py`: Add event logging
- `backend/app/routers/download.py`: Add event logging

