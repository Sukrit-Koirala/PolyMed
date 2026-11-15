from sqlalchemy import update

from .models import NoteDraft, now


def purge_expired_transcripts(db):
    """Purge only source transcripts; approved clinical note content remains unchanged."""
    count = 0
    for hospital in db.local_factories:
        with db.local(hospital) as local:
            result = local.execute(update(NoteDraft).where(NoteDraft.transcript_expires_at < now(), NoteDraft.transcript.is_not(None)).values(transcript=None))
            count += result.rowcount
    return count
