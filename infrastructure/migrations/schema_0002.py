import time
from sqlalchemy import String, Text, ForeignKey, UniqueConstraint, BigInteger, JSON
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm import DeclarativeBase
class Base(DeclarativeBase): pass

def now(): return int(time.time())

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(100))
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    xp: Mapped[int] = mapped_column(default=0)
    coins: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[int] = mapped_column(default=now)

class Session(Base):
    __tablename__ = 'sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    expires_at: Mapped[int]

class Attempt(Base):
    __tablename__ = 'lesson_attempts'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    lesson_id: Mapped[str] = mapped_column(String(80))
    answers: Mapped[list] = mapped_column(JSON, default=list)
    started_at: Mapped[int] = mapped_column(default=now)
    completed_at: Mapped[int | None]
    score: Mapped[int | None]

class Reward(Base):
    __tablename__ = 'rewards'
    __table_args__ = (UniqueConstraint('user_id', 'lesson_id'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    lesson_id: Mapped[str] = mapped_column(String(80))
    xp: Mapped[int]
    coins: Mapped[int]
    created_at: Mapped[int] = mapped_column(default=now)

class Plan(Base):
    __tablename__ = 'subscription_plans'
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    stars: Mapped[int]
    enabled: Mapped[bool] = mapped_column(default=True)

class Order(Base):
    __tablename__ = 'orders'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey('subscription_plans.id'))
    stars: Mapped[int]
    status: Mapped[str] = mapped_column(String(30), default='pending')
    invoice_url: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[int]
    checkout_id: Mapped[str | None] = mapped_column(String(200))
    checkout_at: Mapped[int | None]

class Payment(Base):
    __tablename__ = 'payments'
    charge_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey('orders.id'), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    stars: Mapped[int]
    expires_at: Mapped[int]
    recurring: Mapped[bool] = mapped_column(default=False)
    canceled: Mapped[bool] = mapped_column(default=False)
    refunded: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[int] = mapped_column(default=now)

class Event(Base):
    __tablename__ = 'app_events'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), index=True)
    kind: Mapped[str] = mapped_column(String(80), index=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[int] = mapped_column(default=now, index=True)

class AIUsage(Base):
    __tablename__ = 'ai_usage_records'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    day: Mapped[str] = mapped_column(String(10), index=True)
    status: Mapped[str] = mapped_column(String(20))
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    estimated_usd: Mapped[float] = mapped_column(default=0.0)

class AIMessage(Base):
    __tablename__ = 'ai_messages'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    request_id: Mapped[str] = mapped_column(String(36), unique=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    created_at: Mapped[int] = mapped_column(default=now)

class Assessment(Base):
    __tablename__='assessments'
    id: Mapped[str] = mapped_column(String(36),primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id',ondelete='CASCADE'),index=True)
    answers: Mapped[list] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[int] = mapped_column(default=now)

class Word(Base):
    __tablename__='user_vocabulary'
    __table_args__=(UniqueConstraint('user_id','word'),)
    id: Mapped[str] = mapped_column(String(36),primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id',ondelete='CASCADE'),index=True)
    word: Mapped[str] = mapped_column(String(100))
    translation: Mapped[str] = mapped_column(String(200))
    interval_days: Mapped[int] = mapped_column(default=0)
    due_at: Mapped[int] = mapped_column(default=now,index=True)
    reviews: Mapped[int] = mapped_column(default=0)

class Review(Base):
    __tablename__='vocabulary_reviews'
    id: Mapped[str] = mapped_column(String(36),primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id',ondelete='CASCADE'),index=True)
    word_id: Mapped[str] = mapped_column(ForeignKey('user_vocabulary.id',ondelete='CASCADE'))
    answer: Mapped[str | None] = mapped_column(String(200))
    correct: Mapped[bool | None]
    created_at: Mapped[int] = mapped_column(default=now)

class Achievement(Base):
    __tablename__='user_achievements'
    __table_args__=(UniqueConstraint('user_id','key'),)
    id: Mapped[str] = mapped_column(String(36),primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id',ondelete='CASCADE'),index=True)
    key: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[int] = mapped_column(default=now)

class Cosmetic(Base):
    __tablename__='cosmetic_purchases'
    __table_args__=(UniqueConstraint('user_id','item'),)
    id: Mapped[str] = mapped_column(String(36),primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id',ondelete='CASCADE'),index=True)
    item: Mapped[str] = mapped_column(String(60))
    coins: Mapped[int]
    created_at: Mapped[int] = mapped_column(default=now)

class StoryProgress(Base):
    __tablename__='simulation_progress'
    __table_args__=(UniqueConstraint('user_id','story_id'),)
    id: Mapped[str] = mapped_column(String(36),primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id',ondelete='CASCADE'),index=True)
    story_id: Mapped[str] = mapped_column(String(80))
    index: Mapped[int] = mapped_column(default=0)
    decisions: Mapped[list] = mapped_column(JSON,default=list)
    completed_at: Mapped[int | None]

class Referral(Base):
    __tablename__='referrals'
    invitee_id: Mapped[int] = mapped_column(ForeignKey('users.id'),primary_key=True)
    referrer_id: Mapped[int] = mapped_column(ForeignKey('users.id'),index=True)
    rewarded: Mapped[bool] = mapped_column(default=False)
    revoked: Mapped[bool] = mapped_column(default=False)
    reward_charge_id: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[int] = mapped_column(default=now)

class Notification(Base):
    __tablename__='notifications'
    __table_args__=(UniqueConstraint('user_id','key'),)
    id: Mapped[str] = mapped_column(String(36),primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id',ondelete='CASCADE'),index=True)
    key: Mapped[str] = mapped_column(String(100))
    text: Mapped[str] = mapped_column(Text)
    sent_at: Mapped[int | None]
    created_at: Mapped[int] = mapped_column(default=now)

metadata = Base.metadata
