import json
from datetime import datetime, date, timezone, timedelta
from typing import Optional, List, Dict, Any
from sqlmodel import SQLModel, Field, create_engine, Session, select

# Indian Standard Time (UTC+5:30)
IST = timezone(timedelta(hours=5, minutes=30))

def now_ist() -> datetime:
    """Return current datetime in IST."""
    return datetime.now(IST)

DATABASE_URL = "sqlite:///./stocker.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

class BrokerCredential(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    broker_name: str  # 'kite', 'shoonya', 'dhan', 'fyers', etc.
    api_key: str
    api_secret: str
    totp_secret: Optional[str] = None
    access_token: Optional[str] = None
    active: bool = Field(default=True)
    updated_at: datetime = Field(default_factory=now_ist)

class Strategy(SQLModel, table=True):
    """Strategy template / blueprint. Lives in the library."""
    id: str = Field(primary_key=True)
    name: str
    description: str = Field(default="")
    strategy_type: str = Field(default="custom")  # 'custom' | 'orb_breakout'
    active: bool = Field(default=True)             # kept for backward compat
    paper_trade: bool = Field(default=True)        # kept for backward compat
    config_json: str  # Default / template config
    created_at: datetime = Field(default_factory=now_ist)

    def get_config(self) -> Dict[str, Any]:
        try:
            return json.loads(self.config_json)
        except Exception:
            return {}

class StrategyInstance(SQLModel, table=True):
    """A running deployment of a strategy template on a specific symbol."""
    id: Optional[int] = Field(default=None, primary_key=True)
    template_id: str = Field(index=True)           # FK → Strategy.id
    name: str = Field(default="")                   # display name e.g. "ORB — NIFTY 50"
    symbol: str = Field(default="NSE:NIFTY 50")
    instrument_type: str = Field(default="OPTION")  # 'STOCK' | 'OPTION'
    config_json: str = Field(default="{}")          # instance-specific overrides
    active: bool = Field(default=True)
    paper_trade: bool = Field(default=True)
    created_at: datetime = Field(default_factory=now_ist)

    def get_config(self) -> Dict[str, Any]:
        try:
            return json.loads(self.config_json)
        except Exception:
            return {}

class Trade(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    strategy_id: str                                # template ID (backward compat)
    instance_id: Optional[int] = Field(default=None, index=True)  # FK → StrategyInstance.id
    symbol: str
    option_type: Optional[str] = None  # 'CE', 'PE', or 'EQUITY'
    strike_price: Optional[float] = None
    expiry: Optional[str] = None
    quantity: int
    entry_price: float
    exit_price: Optional[float] = None
    entry_time: datetime = Field(default_factory=now_ist)
    exit_time: Optional[datetime] = None
    status: str = Field(default="OPEN")  # 'OPEN', 'CLOSED', 'CANCELLED'
    mode: str = Field(default="PAPER")  # 'PAPER' or 'LIVE'
    pnl: Optional[float] = Field(default=0.0)
    exit_reason: Optional[str] = None  # 'SL', 'TARGET', 'INDICATOR', 'TIMELINE', 'MANUAL'
    broker_order_id: Optional[str] = None

class DailySummary(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    trade_date: date = Field(default_factory=date.today, unique=True)
    total_trades: int = Field(default=0)
    profitable_trades: int = Field(default=0)
    losing_trades: int = Field(default=0)
    win_rate: float = Field(default=0.0)
    net_pnl: float = Field(default=0.0)
    updated_at: datetime = Field(default_factory=now_ist)

class SystemState(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: str
    updated_at: datetime = Field(default_factory=now_ist)

def init_db():
    """Create all SQLite database tables."""
    SQLModel.metadata.create_all(engine)

def get_session():
    """FastAPI DB session generator dependency."""
    with Session(engine) as session:
        yield session
