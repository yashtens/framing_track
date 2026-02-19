"""
KrishiTrack – Database Models
Tables: Crop, Expense, Labour, Harvest
"""

from datetime import datetime
from extensions import db


class Crop(db.Model):
    __tablename__ = 'crops'

    id               = db.Column(db.Integer, primary_key=True)
    name             = db.Column(db.String(120), nullable=False)
    variety          = db.Column(db.String(120))
    field_area       = db.Column(db.Float, default=0.0)          # in acres
    seeding_date     = db.Column(db.Date, nullable=False)
    expected_harvest = db.Column(db.Date)
    fertilizer_details = db.Column(db.Text)
    water_schedule   = db.Column(db.String(255))
    status           = db.Column(db.String(30), default='Growing')  # Growing / Harvested
    image_path       = db.Column(db.String(255))
    notes            = db.Column(db.Text)
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at       = db.Column(db.DateTime, default=datetime.utcnow,
                                 onupdate=datetime.utcnow)

    # Relationships
    expenses = db.relationship('Expense', backref='crop',
                               lazy=True, cascade='all, delete-orphan')
    labours  = db.relationship('Labour',  backref='crop',
                               lazy=True, cascade='all, delete-orphan')
    harvests = db.relationship('Harvest', backref='crop',
                               lazy=True, cascade='all, delete-orphan')

    @property
    def total_investment(self):
        return sum(e.total for e in self.expenses)

    @property
    def total_income(self):
        return sum(h.total_income for h in self.harvests)

    @property
    def profit_loss(self):
        return self.total_income - self.total_investment

    def __repr__(self):
        return f'<Crop {self.name}>'


class Expense(db.Model):
    __tablename__ = 'expenses'

    id               = db.Column(db.Integer, primary_key=True)
    crop_id          = db.Column(db.Integer, db.ForeignKey('crops.id'), nullable=False)
    date             = db.Column(db.Date, default=datetime.utcnow)
    seeds_cost       = db.Column(db.Float, default=0.0)
    fertilizer_cost  = db.Column(db.Float, default=0.0)
    equipment_cost   = db.Column(db.Float, default=0.0)
    labour_cost      = db.Column(db.Float, default=0.0)
    other_expenses   = db.Column(db.Float, default=0.0)
    notes            = db.Column(db.Text)
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def total(self):
        return (self.seeds_cost + self.fertilizer_cost +
                self.equipment_cost + self.labour_cost + self.other_expenses)

    def __repr__(self):
        return f'<Expense crop_id={self.crop_id} total={self.total}>'


class Labour(db.Model):
    __tablename__ = 'labours'

    id              = db.Column(db.Integer, primary_key=True)
    crop_id         = db.Column(db.Integer, db.ForeignKey('crops.id'), nullable=False)
    name            = db.Column(db.String(120), nullable=False)
    work_type       = db.Column(db.String(120))
    days_worked     = db.Column(db.Float, default=1.0)
    payment_per_day = db.Column(db.Float, default=0.0)
    date            = db.Column(db.Date, default=datetime.utcnow)
    notes           = db.Column(db.Text)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def total_payment(self):
        return self.days_worked * self.payment_per_day

    def __repr__(self):
        return f'<Labour {self.name}>'


class Harvest(db.Model):
    __tablename__ = 'harvests'

    id               = db.Column(db.Integer, primary_key=True)
    crop_id          = db.Column(db.Integer, db.ForeignKey('crops.id'), nullable=False)
    harvest_date     = db.Column(db.Date, nullable=False)
    total_production = db.Column(db.Float, default=0.0)   # kg
    unit             = db.Column(db.String(20), default='kg')
    selling_price    = db.Column(db.Float, default=0.0)   # per unit
    total_income     = db.Column(db.Float, default=0.0)   # auto-set on save
    notes            = db.Column(db.Text)
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)

    def calculate_income(self):
        self.total_income = self.total_production * self.selling_price

    def __repr__(self):
        return f'<Harvest crop_id={self.crop_id} income={self.total_income}>'