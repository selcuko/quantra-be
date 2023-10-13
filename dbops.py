from datetime import datetime
from typing import List
from typing import Optional
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, UniqueConstraint
from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship


class Base(DeclarativeBase):
    pass


class DBMarket(Base):
    __tablename__ = "market"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(30), unique=True)
    trading_enabled: Mapped[Boolean] = mapped_column(Boolean, default=False)
    testnet_enabled: Mapped[Boolean] = mapped_column(Boolean, default=False)
    mainnet_enabled: Mapped[Boolean] = mapped_column(Boolean, default=False)
    config_name: Mapped[Optional[str]] = mapped_column(String(30))
    symbols: Mapped[List["DBSymbol"]] = relationship(back_populates="market")
    def __repr__(self) -> str:
        return f"Market(id={self.id!r})"


class DBSymbol(Base):
    __tablename__ = "symbol"
    __table_args__ = (UniqueConstraint('name', 'market_id', name='no_duplicate_symbols_within_market'),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(30))
    base: Mapped[str] = mapped_column(String(30))
    quote: Mapped[str] = mapped_column(String(30))

    market_id: Mapped[int] = mapped_column(ForeignKey("market.id"))
    market: Mapped["DBMarket"] = relationship(back_populates="symbols")
    sessions: Mapped[List["DBSession"]] = relationship(back_populates="symbol")
    signals: Mapped[List["DBSignal"]] = relationship(back_populates="symbol")

    def __repr__(self) -> str:
        return f"Symbol(id={self.id!r})"


class DBSession(Base):
    __tablename__ = "session"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_type: Mapped[str] = mapped_column(String(30))
    freq: Mapped[str] = mapped_column(String(30))
    started: Mapped[DateTime] = mapped_column(DateTime, default=datetime.utcnow)
    ended: Mapped[Optional[DateTime]] = mapped_column(DateTime)
    symbol_id: Mapped[int] = mapped_column(ForeignKey("symbol.id"))
    symbol: Mapped["DBSymbol"] = relationship(back_populates="sessions")
    subscriptions: Mapped[List["DBSubscription"]] = relationship(back_populates="session")
    def __repr__(self) -> str:
        return f"Session(id={self.id!r})"


class DBSignal(Base):
    __tablename__ = "signal"
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol_id = mapped_column(ForeignKey("symbol.id"))
    symbol: Mapped["DBSymbol"] = relationship(back_populates="signals")
    timestamp: Mapped[DateTime] = mapped_column(DateTime)
    side: Mapped[str] = mapped_column(String(30))
    price: Mapped[float] = mapped_column(Float)
    rawrow: Mapped[str] = mapped_column(String(256))
    orders: Mapped[List["DBOrder"]] = relationship(back_populates="signal")
    def __repr__(self) -> str:
        return f"Signal(id={self.id!r})"


class DBOrder(Base):
    __tablename__ = "order"
    id: Mapped[int] = mapped_column(primary_key=True)
    side: Mapped[str] = mapped_column(String(30))
    size: Mapped[float] = mapped_column(Float)
    quantity: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    order_type: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30))
    timestamp: Mapped[DateTime] = mapped_column(DateTime)
    signal_id: Mapped[int] = mapped_column(ForeignKey("signal.id"))
    signal: Mapped["DBSignal"] = relationship(back_populates="orders")
    def __repr__(self) -> str:
        return f"Order(id={self.id!r})"


class DBUser(Base):
    __tablename__ = "user"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(30))
    subscriptions: Mapped[List["DBSubscription"]] = relationship(back_populates="user")
    def __repr__(self) -> str:
        return f"User(id={self.id!r})"


class DBSubscription(Base):
    __tablename__ = "subscription"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    user: Mapped["DBUser"] = relationship(back_populates="subscriptions")
    session_id: Mapped[int] = mapped_column(ForeignKey("session.id"))
    session: Mapped["DBSession"] = relationship(back_populates="subscriptions")
    external_id: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(128))
    def __repr__(self) -> str:
        return f"Subscription(id={self.id!r})"


from sqlalchemy import create_engine
engine = create_engine("sqlite:///local.sqlite", echo=False)

#Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)

from sqlalchemy.orm import sessionmaker
session = sessionmaker(bind=engine)()

if not (db_binance := session.query(DBMarket).filter_by(name="BINANCE").first()):
    session.add(db_binance := DBMarket(name="BINANCE", config_name="BINANCE-TESTNET", testnet_enabled=True, trading_enabled=True))
if not session.query(DBMarket).filter_by(name="KUCOIN").first():
    session.add(DBMarket(name="KUCOIN", config_name="KUCOIN", mainnet_enabled=True, trading_enabled=True))
if not session.query(DBMarket).filter_by(name="MEXC").first():
    session.add(DBMarket(name="MEXC", config_name="MEXC"))
if not session.query(DBSymbol).filter_by(name="BTC-USDT").first():
    session.add(DBSymbol(name="BTC-USDT", base="BTC", quote="USDT", market=db_binance))
if not session.query(DBSymbol).filter_by(name="ETH-USDT").first():
    session.add(DBSymbol(name="ETH-USDT", base="ETH", quote="USDT", market=db_binance))
if not session.query(DBSymbol).filter_by(name="XRP-USDT").first():
    session.add(DBSymbol(name="XRP-USDT", base="XRP", quote="USDT", market=db_binance))
session.commit()
