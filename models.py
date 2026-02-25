"""
KrishiTrack – Database Models
Tables: Crop, Expense, Labour, Harvest, CropPhoto,
        CropRecommendation, FertilizerRec, PesticideRec, SeasonalAlert
"""

from datetime import datetime
from extensions import db
from werkzeug.security import generate_password_hash, check_password_hash

class Crop(db.Model):
    __tablename__ = 'crops'
    id               = db.Column(db.Integer, primary_key=True)
    name             = db.Column(db.String(120), nullable=False)
    variety          = db.Column(db.String(120))
    field_area       = db.Column(db.Float, default=0.0)
    seeding_date     = db.Column(db.Date, nullable=False)
    expected_harvest = db.Column(db.Date)
    fertilizer_details = db.Column(db.Text)
    water_schedule   = db.Column(db.String(255))
    status           = db.Column(db.String(30), default='Growing')
    image_path       = db.Column(db.String(255))
    notes            = db.Column(db.Text)
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at       = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    expenses  = db.relationship('Expense',   backref='crop', lazy=True, cascade='all, delete-orphan')
    labours   = db.relationship('Labour',    backref='crop', lazy=True, cascade='all, delete-orphan')
    harvests  = db.relationship('Harvest',   backref='crop', lazy=True, cascade='all, delete-orphan')
    photos    = db.relationship('CropPhoto', backref='crop', lazy=True, cascade='all, delete-orphan',
                                order_by='CropPhoto.taken_date')

    @property
    def total_investment(self):
        return sum(e.total for e in self.expenses)

    @property
    def total_income(self):
        return sum(h.total_income for h in self.harvests)

    @property
    def profit_loss(self):
        return self.total_income - self.total_investment

    @property
    def latest_photo(self):
        if self.photos:
            return sorted(self.photos, key=lambda p: p.taken_date, reverse=True)[0]
        return None

    @property
    def total_photos(self):
        return len(self.photos)

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


class Harvest(db.Model):
    __tablename__ = 'harvests'
    id               = db.Column(db.Integer, primary_key=True)
    crop_id          = db.Column(db.Integer, db.ForeignKey('crops.id'), nullable=False)
    harvest_date     = db.Column(db.Date, nullable=False)
    total_production = db.Column(db.Float, default=0.0)
    unit             = db.Column(db.String(20), default='kg')
    selling_price    = db.Column(db.Float, default=0.0)
    total_income     = db.Column(db.Float, default=0.0)
    notes            = db.Column(db.Text)
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)

    def calculate_income(self):
        self.total_income = self.total_production * self.selling_price


class CropPhoto(db.Model):
    __tablename__ = 'crop_photos'
    id           = db.Column(db.Integer, primary_key=True)
    crop_id      = db.Column(db.Integer, db.ForeignKey('crops.id'), nullable=False)
    photo_path   = db.Column(db.String(255), nullable=False)
    caption      = db.Column(db.String(255))
    week_number  = db.Column(db.Integer)
    growth_stage = db.Column(db.String(100))
    taken_date   = db.Column(db.Date, nullable=False)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    GROWTH_STAGES = ['Germination','Seedling','Vegetative Growth',
                     'Flowering','Fruiting','Harvest Ready','Post Harvest']


# ─────────────────────────────────────────────────────────────
#  NEW FEATURE MODELS
# ─────────────────────────────────────────────────────────────

class CropRecommendation(db.Model):
    """Dataset for Smart Crop Recommendation."""
    __tablename__ = 'crop_recommendations'
    id               = db.Column(db.Integer, primary_key=True)
    crop_name        = db.Column(db.String(100), nullable=False)
    season           = db.Column(db.String(30), nullable=False)   # Kharif / Rabi / Summer / All
    soil_type        = db.Column(db.String(50), nullable=False)   # Loamy / Clay / Sandy / Black / Red / Any
    water_req        = db.Column(db.String(30), nullable=False)   # Low / Medium / High
    state            = db.Column(db.String(100))                  # State or 'All India'
    avg_yield_acre   = db.Column(db.Float, default=0.0)           # quintals per acre
    avg_price_quintal= db.Column(db.Float, default=0.0)           # ₹ per quintal
    cost_per_acre    = db.Column(db.Float, default=0.0)           # ₹ total cost per acre
    duration_days    = db.Column(db.Integer, default=90)          # days to harvest
    description      = db.Column(db.Text)
    emoji            = db.Column(db.String(10), default='🌿')

    @property
    def expected_profit_per_acre(self):
        return (self.avg_yield_acre * self.avg_price_quintal) - self.cost_per_acre

    @property
    def roi_percent(self):
        if self.cost_per_acre > 0:
            return round((self.expected_profit_per_acre / self.cost_per_acre) * 100, 1)
        return 0


class FertilizerRecommendation(db.Model):
    """Fertilizer advice by crop + growth stage."""
    __tablename__ = 'fertilizer_recommendations'
    id              = db.Column(db.Integer, primary_key=True)
    crop_name       = db.Column(db.String(100), nullable=False)
    growth_stage    = db.Column(db.String(50), nullable=False)  # Seedling / Vegetative / Flowering / Fruiting
    fertilizer_name = db.Column(db.String(100), nullable=False)
    quantity_acre   = db.Column(db.String(60))                  # e.g. "50 kg"
    timing          = db.Column(db.String(120))                 # e.g. "Apply 20 days after sowing"
    method          = db.Column(db.String(100))                 # Broadcast / Drip / Foliar
    notes           = db.Column(db.Text)
    priority        = db.Column(db.Integer, default=1)         # 1=Primary, 2=Secondary


class PesticideRecommendation(db.Model):
    """Pesticide advice by crop + pest/disease."""
    __tablename__ = 'pesticide_recommendations'
    id              = db.Column(db.Integer, primary_key=True)
    crop_name       = db.Column(db.String(100), nullable=False)
    pest_name       = db.Column(db.String(120), nullable=False)
    pest_type       = db.Column(db.String(30))                  # Insect / Disease / Weed / Mite
    pesticide_name  = db.Column(db.String(120), nullable=False)
    quantity_acre   = db.Column(db.String(60))
    spray_interval  = db.Column(db.String(60))                  # e.g. "Every 10-15 days"
    safety_days     = db.Column(db.Integer, default=7)          # days before harvest safe
    notes           = db.Column(db.Text)


class SeasonalAlert(db.Model):
    """Month-wise crop activity alerts."""
    __tablename__ = 'seasonal_alerts'
    id          = db.Column(db.Integer, primary_key=True)
    month       = db.Column(db.Integer, nullable=False)         # 1-12
    crop_name   = db.Column(db.String(100), nullable=False)
    activity    = db.Column(db.String(120), nullable=False)     # Sow / Irrigate / Harvest / Spray / Apply Fertilizer
    description = db.Column(db.Text)
    priority    = db.Column(db.String(20), default='Normal')    # High / Normal / Low
    emoji       = db.Column(db.String(10), default='🌿')


# ─────────────────────────────────────────────────────────────
#  USER AUTHENTICATION MODEL
# ─────────────────────────────────────────────────────────────

from werkzeug.security import generate_password_hash, check_password_hash

class User(db.Model):
    """Multi-user login — stored in MySQL."""
    __tablename__ = 'users'

    id           = db.Column(db.Integer, primary_key=True)
    username     = db.Column(db.String(80),  unique=True, nullable=False)
    email        = db.Column(db.String(120), unique=True, nullable=False)
    full_name    = db.Column(db.String(120), nullable=False)
    phone        = db.Column(db.String(20))
    password_hash= db.Column(db.String(255), nullable=False)
    role         = db.Column(db.String(20), default='farmer')   # admin / farmer
    is_active    = db.Column(db.Boolean, default=True)
    # Security question for forgot password (no email server needed)
    security_q   = db.Column(db.String(200))
    security_ans = db.Column(db.String(200))
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
    last_login   = db.Column(db.DateTime)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'
        content = content.rstrip() + '\n' + user_model + '\n'