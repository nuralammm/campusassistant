"""Explicit synthetic portal accounts; never overwrite an existing account."""
import os
from campus_assistant.api.db import SessionLocal,User,StudentAccount,Membership
from campus_assistant.api.security import hash_password

def seed_portals(db,password):
    if len(password)<12:raise ValueError('PORTAL_DEMO_PASSWORD requires 12+ characters')
    for username,role in [('mahasiswa','student'),('prodi','prodi')]:
        if db.get(User,username):continue
        db.add(User(id=username,role=role,password_hash=hash_password(password)));db.flush()
        if role=='student':db.add(StudentAccount(user_id=username,student_id='STD-003'))
        else:db.add(Membership(user_id=username,class_id='RPL-01'))
    db.commit()

if __name__=='__main__':
    with SessionLocal() as db:seed_portals(db,os.environ['PORTAL_DEMO_PASSWORD'])
    print('Synthetic portal accounts ready: mahasiswa, prodi')
