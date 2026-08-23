from sqlalchemy import text
from app.data.database import sync_engine

def update_tickets():
    with sync_engine.connect() as conn:
        conn.execute(text("UPDATE tickets SET severity='p1', issue_type='shipment_creation_failure' WHERE id='TKT-501'"))
        conn.execute(text("UPDATE tickets SET severity='p2', known_issue_ref='KI-208', issue_type='bulk_upload_failure' WHERE id='TKT-502'"))
        conn.execute(text("UPDATE tickets SET severity='p3', issue_type='billing' WHERE id='TKT-503'"))
        conn.execute(text("UPDATE tickets SET severity='p2', known_issue_ref='KI-211', issue_type='carrier_sync_delay' WHERE id='TKT-504'"))
        conn.execute(text("UPDATE tickets SET severity='p1', issue_type='security_exposure' WHERE id='TKT-505'"))
        conn.execute(text("UPDATE tickets SET severity='p2', known_issue_ref='KI-208', issue_type='bulk_upload_failure' WHERE id='TKT-451'"))
        conn.commit()
        print("✓ Successfully updated ticket metadata in Postgres")

if __name__ == "__main__":
    update_tickets()
