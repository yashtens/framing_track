"""
KrishiTrack – Smart Farm Management System
Flask Application Entry Point
"""

import os
import csv
import io
from datetime import datetime, date, timedelta
from functools import wraps

from flask import (Flask, render_template, redirect, url_for, request,
                   session, flash, jsonify, send_file, make_response)
from werkzeug.utils import secure_filename
from sqlalchemy import func, extract

from config import Config
from extensions import db


# ─────────────────────────────────────────────────────────────
#  App Factory
# ─────────────────────────────────────────────────────────────

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)

    # Import models AFTER db is initialised
    from models import Crop, Expense, Labour, Harvest

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # ── Context Processors ───────────────────────────────────

    @app.context_processor
    def inject_globals():
        return {'now': datetime.utcnow(), 'today': date.today()}

    # Serve uploaded images
    from flask import send_from_directory

    @app.route('/uploads/<filename>')
    def uploaded_file(filename):
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

    # Also serve from static/uploads for template compatibility
    @app.route('/static/uploads/<filename>')
    def static_upload(filename):
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

    # ── Helpers ──────────────────────────────────────────────

    def allowed_file(filename):
        return ('.' in filename and
                filename.rsplit('.', 1)[1].lower()
                in app.config['ALLOWED_EXTENSIONS'])

    def login_required(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not session.get('logged_in'):
                flash('Please log in first.', 'warning')
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated

    # ── Auth Routes ───────────────────────────────────────────

    @app.route('/', methods=['GET', 'POST'])
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if session.get('logged_in'):
            return redirect(url_for('dashboard'))

        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            if (username == app.config['ADMIN_USERNAME'] and
                    password == app.config['ADMIN_PASSWORD']):
                session['logged_in'] = True
                session['username'] = username
                flash('Welcome back! 🌾', 'success')
                return redirect(url_for('dashboard'))
            flash('Invalid username or password.', 'danger')

        return render_template('login.html')

    @app.route('/logout')
    def logout():
        session.clear()
        flash('Logged out successfully.', 'info')
        return redirect(url_for('login'))

    # ── Dashboard ─────────────────────────────────────────────

    @app.route('/dashboard')
    @login_required
    def dashboard():
        total_crops      = Crop.query.count()
        growing_crops    = Crop.query.filter_by(status='Growing').count()
        harvested_crops  = Crop.query.filter_by(status='Harvested').count()

        # Totals
        all_crops = Crop.query.all()
        total_investment = sum(c.total_investment for c in all_crops)
        total_income     = sum(c.total_income     for c in all_crops)
        profit_loss      = total_income - total_investment

        # Recent crops (last 5)
        recent_crops = (Crop.query
                        .order_by(Crop.created_at.desc())
                        .limit(5).all())

        # Monthly expenses for chart (last 6 months)
        six_months_ago = date.today() - timedelta(days=180)
        monthly_data = (db.session.query(
                            extract('year',  Expense.date).label('yr'),
                            extract('month', Expense.date).label('mo'),
                            func.sum(
                                Expense.seeds_cost + Expense.fertilizer_cost +
                                Expense.equipment_cost + Expense.labour_cost +
                                Expense.other_expenses
                            ).label('total')
                        )
                        .filter(Expense.date >= six_months_ago)
                        .group_by('yr', 'mo')
                        .order_by('yr', 'mo')
                        .all())

        chart_labels  = []
        chart_expense = []
        month_names   = ['Jan','Feb','Mar','Apr','May','Jun',
                         'Jul','Aug','Sep','Oct','Nov','Dec']
        for row in monthly_data:
            chart_labels.append(f"{month_names[int(row.mo)-1]} {int(row.yr)}")
            chart_expense.append(float(row.total or 0))

        # Crop profit chart data
        crop_names   = [c.name for c in all_crops]
        crop_profits = [c.profit_loss for c in all_crops]

        # Upcoming harvests (next 30 days)
        upcoming = (Crop.query
                    .filter(Crop.expected_harvest >= date.today(),
                            Crop.expected_harvest <= date.today() + timedelta(days=30),
                            Crop.status == 'Growing')
                    .order_by(Crop.expected_harvest)
                    .all())

        return render_template('dashboard.html',
            total_crops=total_crops,
            growing_crops=growing_crops,
            harvested_crops=harvested_crops,
            total_investment=total_investment,
            total_income=total_income,
            profit_loss=profit_loss,
            recent_crops=recent_crops,
            chart_labels=chart_labels,
            chart_expense=chart_expense,
            crop_names=crop_names,
            crop_profits=crop_profits,
            upcoming=upcoming,
        )

    # ── Crop Routes ───────────────────────────────────────────

    @app.route('/crops')
    @login_required
    def crops():
        status_filter = request.args.get('status', '')
        q = request.args.get('q', '')
        query = Crop.query
        if status_filter:
            query = query.filter_by(status=status_filter)
        if q:
            query = query.filter(Crop.name.ilike(f'%{q}%'))
        all_crops = query.order_by(Crop.created_at.desc()).all()
        return render_template('crops.html', crops=all_crops,
                               status_filter=status_filter, q=q)

    @app.route('/crops/add', methods=['GET', 'POST'])
    @login_required
    def crop_add():
        if request.method == 'POST':
            image_path = None
            if 'image' in request.files:
                file = request.files['image']
                if file and file.filename and allowed_file(file.filename):
                    filename  = secure_filename(file.filename)
                    filename  = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    image_path = filename

            crop = Crop(
                name              = request.form['name'],
                variety           = request.form.get('variety', ''),
                field_area        = float(request.form.get('field_area') or 0),
                seeding_date      = datetime.strptime(request.form['seeding_date'], '%Y-%m-%d').date(),
                expected_harvest  = (datetime.strptime(request.form['expected_harvest'], '%Y-%m-%d').date()
                                     if request.form.get('expected_harvest') else None),
                fertilizer_details= request.form.get('fertilizer_details', ''),
                water_schedule    = request.form.get('water_schedule', ''),
                status            = request.form.get('status', 'Growing'),
                notes             = request.form.get('notes', ''),
                image_path        = image_path,
            )
            db.session.add(crop)
            db.session.commit()
            flash(f'Crop "{crop.name}" added successfully! 🌱', 'success')
            return redirect(url_for('crops'))

        return render_template('crop_form.html', crop=None)

    @app.route('/crops/<int:crop_id>')
    @login_required
    def crop_detail(crop_id):
        crop = Crop.query.get_or_404(crop_id)
        return render_template('crop_detail.html', crop=crop)

    @app.route('/crops/<int:crop_id>/edit', methods=['GET', 'POST'])
    @login_required
    def crop_edit(crop_id):
        crop = Crop.query.get_or_404(crop_id)
        if request.method == 'POST':
            crop.name               = request.form['name']
            crop.variety            = request.form.get('variety', '')
            crop.field_area         = float(request.form.get('field_area') or 0)
            crop.seeding_date       = datetime.strptime(request.form['seeding_date'], '%Y-%m-%d').date()
            crop.expected_harvest   = (datetime.strptime(request.form['expected_harvest'], '%Y-%m-%d').date()
                                       if request.form.get('expected_harvest') else None)
            crop.fertilizer_details = request.form.get('fertilizer_details', '')
            crop.water_schedule     = request.form.get('water_schedule', '')
            crop.status             = request.form.get('status', 'Growing')
            crop.notes              = request.form.get('notes', '')

            if 'image' in request.files:
                file = request.files['image']
                if file and file.filename and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    crop.image_path = filename

            db.session.commit()
            flash(f'Crop "{crop.name}" updated! ✅', 'success')
            return redirect(url_for('crop_detail', crop_id=crop.id))

        return render_template('crop_form.html', crop=crop)

    @app.route('/crops/<int:crop_id>/delete', methods=['POST'])
    @login_required
    def crop_delete(crop_id):
        crop = Crop.query.get_or_404(crop_id)
        name = crop.name
        db.session.delete(crop)
        db.session.commit()
        flash(f'Crop "{name}" deleted.', 'info')
        return redirect(url_for('crops'))

    # ── Expense Routes ────────────────────────────────────────

    @app.route('/expenses')
    @login_required
    def expenses():
        all_crops = Crop.query.order_by(Crop.name).all()
        crop_id   = request.args.get('crop_id', type=int)
        query = Expense.query
        if crop_id:
            query = query.filter_by(crop_id=crop_id)
        all_expenses = query.order_by(Expense.date.desc()).all()

        # Summary
        grand_total = sum(e.total for e in all_expenses)
        return render_template('expenses.html',
                               expenses=all_expenses,
                               crops=all_crops,
                               selected_crop=crop_id,
                               grand_total=grand_total)

    @app.route('/expenses/add', methods=['GET', 'POST'])
    @login_required
    def expense_add():
        crops = Crop.query.order_by(Crop.name).all()
        if request.method == 'POST':
            expense = Expense(
                crop_id         = int(request.form['crop_id']),
                date            = datetime.strptime(request.form['date'], '%Y-%m-%d').date(),
                seeds_cost      = float(request.form.get('seeds_cost')      or 0),
                fertilizer_cost = float(request.form.get('fertilizer_cost') or 0),
                equipment_cost  = float(request.form.get('equipment_cost')  or 0),
                labour_cost     = float(request.form.get('labour_cost')     or 0),
                other_expenses  = float(request.form.get('other_expenses')  or 0),
                notes           = request.form.get('notes', ''),
            )
            db.session.add(expense)
            db.session.commit()
            flash('Expense recorded! 💰', 'success')
            return redirect(url_for('expenses'))
        return render_template('expense_form.html', expense=None, crops=crops)

    @app.route('/expenses/<int:exp_id>/edit', methods=['GET', 'POST'])
    @login_required
    def expense_edit(exp_id):
        expense = Expense.query.get_or_404(exp_id)
        crops   = Crop.query.order_by(Crop.name).all()
        if request.method == 'POST':
            expense.crop_id         = int(request.form['crop_id'])
            expense.date            = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
            expense.seeds_cost      = float(request.form.get('seeds_cost')      or 0)
            expense.fertilizer_cost = float(request.form.get('fertilizer_cost') or 0)
            expense.equipment_cost  = float(request.form.get('equipment_cost')  or 0)
            expense.labour_cost     = float(request.form.get('labour_cost')     or 0)
            expense.other_expenses  = float(request.form.get('other_expenses')  or 0)
            expense.notes           = request.form.get('notes', '')
            db.session.commit()
            flash('Expense updated! ✅', 'success')
            return redirect(url_for('expenses'))
        return render_template('expense_form.html', expense=expense, crops=crops)

    @app.route('/expenses/<int:exp_id>/delete', methods=['POST'])
    @login_required
    def expense_delete(exp_id):
        expense = Expense.query.get_or_404(exp_id)
        db.session.delete(expense)
        db.session.commit()
        flash('Expense deleted.', 'info')
        return redirect(url_for('expenses'))

    # ── Labour Routes ─────────────────────────────────────────

    @app.route('/labour')
    @login_required
    def labour():
        crop_id = request.args.get('crop_id', type=int)
        crops   = Crop.query.order_by(Crop.name).all()
        query   = Labour.query
        if crop_id:
            query = query.filter_by(crop_id=crop_id)
        labours = query.order_by(Labour.date.desc()).all()
        total_payment = sum(l.total_payment for l in labours)
        return render_template('labour.html',
                               labours=labours,
                               crops=crops,
                               selected_crop=crop_id,
                               total_payment=total_payment)

    @app.route('/labour/add', methods=['GET', 'POST'])
    @login_required
    def labour_add():
        crops = Crop.query.order_by(Crop.name).all()
        if request.method == 'POST':
            labour = Labour(
                crop_id         = int(request.form['crop_id']),
                name            = request.form['name'],
                work_type       = request.form.get('work_type', ''),
                days_worked     = float(request.form.get('days_worked') or 1),
                payment_per_day = float(request.form.get('payment_per_day') or 0),
                date            = datetime.strptime(request.form['date'], '%Y-%m-%d').date(),
                notes           = request.form.get('notes', ''),
            )
            db.session.add(labour)
            db.session.commit()
            flash(f'Labour "{labour.name}" added! 👷', 'success')
            return redirect(url_for('labour'))
        return render_template('labour_form.html', labour=None, crops=crops)

    @app.route('/labour/<int:lab_id>/edit', methods=['GET', 'POST'])
    @login_required
    def labour_edit(lab_id):
        labour = Labour.query.get_or_404(lab_id)
        crops  = Crop.query.order_by(Crop.name).all()
        if request.method == 'POST':
            labour.crop_id         = int(request.form['crop_id'])
            labour.name            = request.form['name']
            labour.work_type       = request.form.get('work_type', '')
            labour.days_worked     = float(request.form.get('days_worked') or 1)
            labour.payment_per_day = float(request.form.get('payment_per_day') or 0)
            labour.date            = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
            labour.notes           = request.form.get('notes', '')
            db.session.commit()
            flash('Labour record updated! ✅', 'success')
            return redirect(url_for('labour'))
        return render_template('labour_form.html', labour=labour, crops=crops)

    @app.route('/labour/<int:lab_id>/delete', methods=['POST'])
    @login_required
    def labour_delete(lab_id):
        labour = Labour.query.get_or_404(lab_id)
        db.session.delete(labour)
        db.session.commit()
        flash('Labour record deleted.', 'info')
        return redirect(url_for('labour'))

    # ── Harvest Routes ────────────────────────────────────────

    @app.route('/harvest')
    @login_required
    def harvest():
        crop_id  = request.args.get('crop_id', type=int)
        crops    = Crop.query.order_by(Crop.name).all()
        query    = Harvest.query
        if crop_id:
            query = query.filter_by(crop_id=crop_id)
        harvests = query.order_by(Harvest.harvest_date.desc()).all()
        total_production = sum(h.total_production for h in harvests)
        total_income     = sum(h.total_income     for h in harvests)
        return render_template('harvest.html',
                               harvests=harvests,
                               crops=crops,
                               selected_crop=crop_id,
                               total_production=total_production,
                               total_income=total_income)

    @app.route('/harvest/add', methods=['GET', 'POST'])
    @login_required
    def harvest_add():
        crops = Crop.query.order_by(Crop.name).all()
        if request.method == 'POST':
            harvest = Harvest(
                crop_id          = int(request.form['crop_id']),
                harvest_date     = datetime.strptime(request.form['harvest_date'], '%Y-%m-%d').date(),
                total_production = float(request.form.get('total_production') or 0),
                unit             = request.form.get('unit', 'kg'),
                selling_price    = float(request.form.get('selling_price') or 0),
                notes            = request.form.get('notes', ''),
            )
            harvest.calculate_income()

            # Mark crop as Harvested
            crop = Crop.query.get(harvest.crop_id)
            if crop:
                crop.status = 'Harvested'

            db.session.add(harvest)
            db.session.commit()
            flash('Harvest recorded! 🌾', 'success')
            return redirect(url_for('harvest'))
        return render_template('harvest_form.html', harvest=None, crops=crops)

    @app.route('/harvest/<int:h_id>/edit', methods=['GET', 'POST'])
    @login_required
    def harvest_edit(h_id):
        harvest = Harvest.query.get_or_404(h_id)
        crops   = Crop.query.order_by(Crop.name).all()
        if request.method == 'POST':
            harvest.crop_id          = int(request.form['crop_id'])
            harvest.harvest_date     = datetime.strptime(request.form['harvest_date'], '%Y-%m-%d').date()
            harvest.total_production = float(request.form.get('total_production') or 0)
            harvest.unit             = request.form.get('unit', 'kg')
            harvest.selling_price    = float(request.form.get('selling_price') or 0)
            harvest.notes            = request.form.get('notes', '')
            harvest.calculate_income()
            db.session.commit()
            flash('Harvest updated! ✅', 'success')
            return redirect(url_for('harvest'))
        return render_template('harvest_form.html', harvest=harvest, crops=crops)

    @app.route('/harvest/<int:h_id>/delete', methods=['POST'])
    @login_required
    def harvest_delete(h_id):
        harvest = Harvest.query.get_or_404(h_id)
        db.session.delete(harvest)
        db.session.commit()
        flash('Harvest record deleted.', 'info')
        return redirect(url_for('harvest'))

    # ── Profit Summary ────────────────────────────────────────

    @app.route('/profit')
    @login_required
    def profit():
        crops = Crop.query.order_by(Crop.name).all()
        summary = []
        for crop in crops:
            inv  = crop.total_investment
            inc  = crop.total_income
            pl   = inc - inv
            summary.append({
                'crop':       crop,
                'investment': inv,
                'income':     inc,
                'profit':     pl,
                'pct':        round((pl / inv * 100) if inv else 0, 1),
            })
        grand_inv    = sum(s['investment'] for s in summary)
        grand_inc    = sum(s['income']     for s in summary)
        grand_pl     = grand_inc - grand_inv
        return render_template('profit.html',
                               summary=summary,
                               grand_inv=grand_inv,
                               grand_inc=grand_inc,
                               grand_pl=grand_pl)

    # ── Reports & CSV Export ──────────────────────────────────

    @app.route('/reports')
    @login_required
    def reports():
        crops = Crop.query.order_by(Crop.name).all()
        return render_template('reports.html', crops=crops)

    @app.route('/reports/export/crops')
    @login_required
    def export_crops():
        crops = Crop.query.all()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['ID','Name','Variety','Area(acres)','Seeding Date',
                         'Expected Harvest','Status','Investment (₹)','Income (₹)','Profit/Loss (₹)'])
        for c in crops:
            writer.writerow([c.id, c.name, c.variety, c.field_area,
                             c.seeding_date, c.expected_harvest, c.status,
                             c.total_investment, c.total_income, c.profit_loss])
        output.seek(0)
        return send_file(io.BytesIO(output.getvalue().encode()),
                         mimetype='text/csv',
                         download_name='crops_report.csv',
                         as_attachment=True)

    @app.route('/reports/export/expenses')
    @login_required
    def export_expenses():
        month = request.args.get('month', type=int)
        year  = request.args.get('year',  type=int)
        query = Expense.query
        if month and year:
            query = query.filter(
                extract('month', Expense.date) == month,
                extract('year',  Expense.date) == year,
            )
        expenses = query.order_by(Expense.date).all()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['ID','Crop','Date','Seeds','Fertilizer','Equipment',
                         'Labour','Other','Total (₹)','Notes'])
        for e in expenses:
            writer.writerow([e.id, e.crop.name, e.date,
                             e.seeds_cost, e.fertilizer_cost,
                             e.equipment_cost, e.labour_cost,
                             e.other_expenses, e.total, e.notes])
        output.seek(0)
        return send_file(io.BytesIO(output.getvalue().encode()),
                         mimetype='text/csv',
                         download_name='expenses_report.csv',
                         as_attachment=True)

    @app.route('/reports/export/labour')
    @login_required
    def export_labour():
        labours = Labour.query.order_by(Labour.date).all()
        output  = io.StringIO()
        writer  = csv.writer(output)
        writer.writerow(['ID','Crop','Name','Work Type','Days Worked',
                         'Pay/Day (₹)','Total Pay (₹)','Date','Notes'])
        for l in labours:
            writer.writerow([l.id, l.crop.name, l.name, l.work_type,
                             l.days_worked, l.payment_per_day,
                             l.total_payment, l.date, l.notes])
        output.seek(0)
        return send_file(io.BytesIO(output.getvalue().encode()),
                         mimetype='text/csv',
                         download_name='labour_report.csv',
                         as_attachment=True)

    @app.route('/reports/export/harvest')
    @login_required
    def export_harvest():
        harvests = Harvest.query.order_by(Harvest.harvest_date).all()
        output   = io.StringIO()
        writer   = csv.writer(output)
        writer.writerow(['ID','Crop','Harvest Date','Production','Unit',
                         'Price/Unit (₹)','Total Income (₹)','Notes'])
        for h in harvests:
            writer.writerow([h.id, h.crop.name, h.harvest_date,
                             h.total_production, h.unit,
                             h.selling_price, h.total_income, h.notes])
        output.seek(0)
        return send_file(io.BytesIO(output.getvalue().encode()),
                         mimetype='text/csv',
                         download_name='harvest_report.csv',
                         as_attachment=True)

    # ── API: auto-calc helpers (JSON) ─────────────────────────

    @app.route('/api/expense-total', methods=['POST'])
    @login_required
    def api_expense_total():
        data = request.json or {}
        total = (float(data.get('seeds',0)) + float(data.get('fertilizer',0)) +
                 float(data.get('equipment',0)) + float(data.get('labour',0)) +
                 float(data.get('other',0)))
        return jsonify({'total': round(total, 2)})

    # ── DB Init ───────────────────────────────────────────────

    @app.cli.command('init-db')
    def init_db():
        """Create all tables and seed sample data."""
        db.create_all()
        seed_sample_data(Crop, Expense, Labour, Harvest)
        print("✅  Database initialised with sample data.")

    return app


def seed_sample_data(Crop, Expense, Labour, Harvest):
    """Insert sample data for demonstration."""
    if Crop.query.count() > 0:
        return  # Already seeded

    from datetime import date
    # Crops
    wheat = Crop(name='Wheat', variety='GW-322', field_area=2.5,
                 seeding_date=date(2024, 11, 1),
                 expected_harvest=date(2025, 3, 15),
                 fertilizer_details='DAP 50kg, Urea 30kg per acre',
                 water_schedule='Every 10 days', status='Growing',
                 notes='Rabi season crop')
    tomato = Crop(name='Tomato', variety='Hybrid-100', field_area=1.0,
                  seeding_date=date(2024, 9, 10),
                  expected_harvest=date(2024, 12, 20),
                  fertilizer_details='NPK 19-19-19',
                  water_schedule='Daily drip irrigation', status='Harvested',
                  notes='Vegetable crop for local market')
    db.session.add_all([wheat, tomato])
    db.session.flush()

    # Expenses
    db.session.add_all([
        Expense(crop_id=wheat.id, date=date(2024, 11, 1),
                seeds_cost=3500, fertilizer_cost=4200,
                equipment_cost=1500, labour_cost=2000, other_expenses=500),
        Expense(crop_id=tomato.id, date=date(2024, 9, 10),
                seeds_cost=1800, fertilizer_cost=2500,
                equipment_cost=800, labour_cost=3000, other_expenses=300),
    ])

    # Labour
    db.session.add_all([
        Labour(crop_id=wheat.id, name='Ramesh Kumar', work_type='Sowing',
               days_worked=3, payment_per_day=400, date=date(2024, 11, 2)),
        Labour(crop_id=tomato.id, name='Suresh Yadav', work_type='Harvesting',
               days_worked=5, payment_per_day=450, date=date(2024, 12, 18)),
    ])

    # Harvest
    h = Harvest(crop_id=tomato.id, harvest_date=date(2024, 12, 20),
                total_production=2200, unit='kg', selling_price=18, notes='Good yield')
    h.calculate_income()
    db.session.add(h)

    db.session.commit()


# ─────────────────────────────────────────────────────────────
#  Entry Point
# ─────────────────────────────────────────────────────────────

app = create_app()

if __name__ == '__main__':
    app.run(debug=True, port=5000)