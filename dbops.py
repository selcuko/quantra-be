from datetime import datetime
from typing import List
from typing import Optional
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, UniqueConstraint
from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship
from telegram import endpoint as telegram_endpoint


class Base(DeclarativeBase):
    pass


class DBMarket(Base):
    __tablename__ = "market"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(30))
    friendly_name: Mapped[Optional[str]] = mapped_column(String(30), unique=True)
    trading_enabled: Mapped[Boolean] = mapped_column(Boolean, default=False)
    testnet_enabled: Mapped[Boolean] = mapped_column(Boolean, default=False)
    mainnet_enabled: Mapped[Boolean] = mapped_column(Boolean, default=False)
    config_name: Mapped[Optional[str]] = mapped_column(String(30), unique=True)
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
    strategy: Mapped[str] = mapped_column(String(30))
    strategy_parameters: Mapped[str] = mapped_column(String(256))
    planned_shutdown: Mapped[Optional[DateTime]] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(30))
    testman_dir: Mapped[Optional[str]] = mapped_column(String(256))
    signals: Mapped[List["DBSignal"]] = relationship(back_populates="session")
    last_heartbeat: Mapped[Optional[DateTime]] = mapped_column(DateTime)

    def __repr__(self) -> str:
        return f"Session(id={self.id!r})"

    def notify(self, message: str):
        errored = []
        for sub in self.subscriptions:
            try:
                sub.notify(message)
            except Exception as e:
                errored.append({
                    "subscription": sub,
                    "exception": e
                })
        return errored

    def heartbeat(self):
        self.last_heartbeat = datetime.utcnow()


class DBSignal(Base):
    __tablename__ = "signal"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id = mapped_column(ForeignKey("session.id"))
    session: Mapped["DBSession"] = relationship(back_populates="signals")
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
    endpoints: Mapped[List["DBEndpoint"]] = relationship(back_populates="user")
    
    def __repr__(self) -> str:
        return f"User(id={self.id!r})"
    
    def notify(self, message: str):
        errored = []
        for endpoint in self.endpoints:
            try:
                endpoint.dispatch(message)
            except Exception as e:
                errored.append({
                    "endpoint": endpoint,
                    "exception": e
                })
        return errored


class DBSubscription(Base):
    __tablename__ = "subscription"
    __table_args__ = (UniqueConstraint('user_id', 'session_id', name='no_duplicate_subscriptions'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    user: Mapped["DBUser"] = relationship(back_populates="subscriptions")
    session_id: Mapped[int] = mapped_column(ForeignKey("session.id"))
    session: Mapped["DBSession"] = relationship(back_populates="subscriptions")
    
    def __repr__(self) -> str:
        return f"Subscription(id={self.id!r})"
    
    def notify(self, message: str):
        return self.user.notify(message)


class DBEndpoint(Base):
    __tablename__ = "endpoint"
    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(30))
    external_id: Mapped[str] = mapped_column(String(128))
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    user: Mapped["DBUser"] = relationship(back_populates="endpoints")

    def __repr__(self) -> str:
        return f"Endpoint(id={self.id!r})"
    
    def dispatch(self, message: str):
        if self.type.lower() == 'telegram':
            return telegram_endpoint(int(self.external_id), message)
        else:
            raise NotImplementedError(f'Endpoint type {self.type} not implemented')


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
if not (user := session.query(DBUser).filter_by(name="master").first()):
    session.add(user := DBUser(name="master"))
if not (endpoint := session.query(DBEndpoint).filter_by(external_id="000000000").first()):
    endpoint = session.add(DBEndpoint(type="telegram", external_id="000000000", user_id=1))
session.commit()
