"""
KrishiTrack – Smart Farm Management System
Flask Application – Complete Ready-to-Run File
"""

import os
import csv
import io
from datetime import datetime, date, timedelta
from functools import wraps
import pymysql
pymysql.install_as_MySQLdb()

from flask import (Flask, render_template, redirect, url_for, request,
                   session, flash, jsonify, send_file, make_response,
                   send_from_directory)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
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
    from models import (Crop, Expense, Labour, Harvest, CropPhoto,
                        CropRecommendation, FertilizerRecommendation,
                        PesticideRecommendation, SeasonalAlert, User)

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'crop_photos'), exist_ok=True)

    # ── Context Processor ────────────────────────────────────

    @app.context_processor
    def inject_globals():
        current_user = None
        if session.get('user_id'):
            current_user = User.query.get(session['user_id'])
        return {
            'now':          datetime.utcnow(),
            'today':        date.today(),
            'current_user': current_user,
        }

    # ── Static File Helpers ──────────────────────────────────

    @app.route('/uploads/<filename>')
    def uploaded_file(filename):
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

    @app.route('/static/uploads/<filename>')
    def static_upload(filename):
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

    @app.route('/uploads/crop_photos/<filename>')
    def serve_crop_photo(filename):
        return send_from_directory(
            os.path.join(app.config['UPLOAD_FOLDER'], 'crop_photos'), filename)

    # ── Utility Helpers ──────────────────────────────────────

    def allowed_file(filename):
        return ('.' in filename and
                filename.rsplit('.', 1)[1].lower()
                in app.config['ALLOWED_EXTENSIONS'])

    def login_required(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not session.get('logged_in'):
                flash('Please log in to continue.', 'warning')
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated

    # ═════════════════════════════════════════════════════════
    #  AUTH ROUTES
    # ═════════════════════════════════════════════════════════

    @app.route('/', methods=['GET', 'POST'])
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if session.get('logged_in'):
            return redirect(url_for('dashboard'))

        if request.method == 'POST':
            username = request.form.get('username', '').strip().lower()
            password = request.form.get('password', '')
            remember = request.form.get('remember')

            user = User.query.filter(
                (User.username == username) | (User.email == username)
            ).first()

            if user and user.is_active and user.check_password(password):
                session['logged_in'] = True
                session['user_id']   = user.id
                session['username']  = user.username
                session['full_name'] = user.full_name
                session['user_role'] = user.role
                if remember:
                    session.permanent = True
                    app.permanent_session_lifetime = timedelta(days=30)
                user.last_login = datetime.utcnow()
                db.session.commit()
                flash(f'Welcome back, {user.full_name}! 🌾', 'success')
                return redirect(url_for('dashboard'))
            elif user and not user.is_active:
                flash('Your account is deactivated. Contact admin.', 'danger')
            else:
                flash('Invalid username/email or password.', 'danger')

        return render_template('login.html')

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if session.get('logged_in'):
            return redirect(url_for('dashboard'))

        if request.method == 'POST':
            full_name  = request.form.get('full_name', '').strip()
            username   = request.form.get('username', '').strip().lower()
            email      = request.form.get('email', '').strip().lower()
            phone      = request.form.get('phone', '').strip()
            password   = request.form.get('password', '')
            confirm_pw = request.form.get('confirm_password', '')
            security_q = request.form.get('security_q', '')
            security_a = request.form.get('security_ans', '').strip().lower()

            errors = []
            if not full_name:         errors.append('Full name is required.')
            if len(username) < 3:     errors.append('Username must be at least 3 characters.')
            if '@' not in email:      errors.append('Enter a valid email address.')
            if len(password) < 6:     errors.append('Password must be at least 6 characters.')
            if password != confirm_pw: errors.append('Passwords do not match.')
            if not security_q or not security_a:
                errors.append('Security question and answer are required.')

            if not errors:
                if User.query.filter_by(username=username).first():
                    errors.append('Username already taken. Choose another.')
                if User.query.filter_by(email=email).first():
                    errors.append('Email already registered. Try logging in.')

            if errors:
                for e in errors:
                    flash(e, 'danger')
                return render_template('register.html',
                    full_name=full_name, username=username,
                    email=email, phone=phone)

            is_first = User.query.count() == 0
            new_user = User(
                full_name    = full_name,
                username     = username,
                email        = email,
                phone        = phone,
                role         = 'admin' if is_first else 'farmer',
                security_q   = security_q,
                security_ans = generate_password_hash(security_a),
            )
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()

            role_msg = ' (Admin — first account)' if is_first else ''
            flash(f'Account created{role_msg}! You can now login. 🎉', 'success')
            return redirect(url_for('login'))

        return render_template('register.html')

    @app.route('/forgot-password', methods=['GET', 'POST'])
    def forgot_password():
        if session.get('logged_in'):
            return redirect(url_for('dashboard'))

        step     = request.args.get('step', '1')
        username = request.args.get('u', '')

        if request.method == 'POST':
            step = request.form.get('step', '1')

            if step == '1':
                username   = request.form.get('username', '').strip().lower()
                security_a = request.form.get('security_ans', '').strip().lower()
                user = User.query.filter(
                    (User.username == username) | (User.email == username)
                ).first()
                if user and user.security_ans and check_password_hash(user.security_ans, security_a):
                    return redirect(url_for('forgot_password', step='2', u=user.username))
                flash('Username or security answer is incorrect.', 'danger')
                return render_template('forgot_password.html', step='1')

            elif step == '2':
                username   = request.form.get('username', '').strip().lower()
                password   = request.form.get('password', '')
                confirm_pw = request.form.get('confirm_password', '')
                if len(password) < 6:
                    flash('Password must be at least 6 characters.', 'danger')
                    return render_template('forgot_password.html', step='2', username=username)
                if password != confirm_pw:
                    flash('Passwords do not match.', 'danger')
                    return render_template('forgot_password.html', step='2', username=username)
                user = User.query.filter_by(username=username).first()
                if user:
                    user.set_password(password)
                    db.session.commit()
                    flash('Password reset successfully! Please login. ✅', 'success')
                    return redirect(url_for('login'))
                flash('User not found.', 'danger')

        return render_template('forgot_password.html', step=step, username=username)

    @app.route('/logout')
    def logout():
        session.clear()
        flash('Logged out successfully. See you soon! 👋', 'info')
        return redirect(url_for('login'))

    @app.route('/profile', methods=['GET', 'POST'])
    @login_required
    def user_profile():
        user = User.query.get(session.get('user_id'))
        if not user:
            session.clear()
            return redirect(url_for('login'))

        if request.method == 'POST':
            action = request.form.get('action')

            if action == 'update_info':
                user.full_name = request.form.get('full_name', user.full_name).strip()
                user.phone     = request.form.get('phone', user.phone or '').strip()
                db.session.commit()
                session['full_name'] = user.full_name
                flash('Profile updated successfully! ✅', 'success')

            elif action == 'change_password':
                old_pw  = request.form.get('old_password', '')
                new_pw  = request.form.get('new_password', '')
                conf_pw = request.form.get('confirm_password', '')
                if not user.check_password(old_pw):
                    flash('Current password is incorrect.', 'danger')
                elif len(new_pw) < 6:
                    flash('New password must be at least 6 characters.', 'danger')
                elif new_pw != conf_pw:
                    flash('New passwords do not match.', 'danger')
                else:
                    user.set_password(new_pw)
                    db.session.commit()
                    flash('Password changed successfully! ✅', 'success')

        return render_template('user_profile.html', user=user)

    # ═════════════════════════════════════════════════════════
    #  DASHBOARD
    # ═════════════════════════════════════════════════════════

    @app.route('/dashboard')
    @login_required
    def dashboard():
        total_crops     = Crop.query.count()
        growing_crops   = Crop.query.filter_by(status='Growing').count()
        harvested_crops = Crop.query.filter_by(status='Harvested').count()

        all_crops        = Crop.query.all()
        total_investment = sum(c.total_investment for c in all_crops)
        total_income     = sum(c.total_income     for c in all_crops)
        profit_loss      = total_income - total_investment

        recent_crops = Crop.query.order_by(Crop.created_at.desc()).limit(5).all()

        # Monthly expenses chart (last 6 months)
        six_months_ago = date.today() - timedelta(days=180)
        monthly_data = (db.session.query(
                            extract('year',  Expense.date).label('yr'),
                            extract('month', Expense.date).label('mo'),
                            func.sum(
                                Expense.seeds_cost + Expense.fertilizer_cost +
                                Expense.equipment_cost + Expense.labour_cost +
                                Expense.other_expenses
                            ).label('total'))
                        .filter(Expense.date >= six_months_ago)
                        .group_by('yr', 'mo')
                        .order_by('yr', 'mo')
                        .all())

        month_names   = ['Jan','Feb','Mar','Apr','May','Jun',
                         'Jul','Aug','Sep','Oct','Nov','Dec']
        chart_labels  = []
        chart_expense = []
        for row in monthly_data:
            chart_labels.append(f"{month_names[int(row.mo)-1]} {int(row.yr)}")
            chart_expense.append(float(row.total or 0))

        crop_names   = [c.name for c in all_crops]
        crop_profits = [c.profit_loss for c in all_crops]

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

    # ═════════════════════════════════════════════════════════
    #  CROP ROUTES
    # ═════════════════════════════════════════════════════════

    @app.route('/crops')
    @login_required
    def crops():
        status_filter = request.args.get('status', '')
        q             = request.args.get('q', '')
        query         = Crop.query
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
                    filename   = secure_filename(file.filename)
                    filename   = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    image_path = filename

            crop = Crop(
                name               = request.form['name'],
                variety            = request.form.get('variety', ''),
                field_area         = float(request.form.get('field_area') or 0),
                seeding_date       = datetime.strptime(request.form['seeding_date'], '%Y-%m-%d').date(),
                expected_harvest   = (datetime.strptime(request.form['expected_harvest'], '%Y-%m-%d').date()
                                      if request.form.get('expected_harvest') else None),
                fertilizer_details = request.form.get('fertilizer_details', ''),
                water_schedule     = request.form.get('water_schedule', ''),
                status             = request.form.get('status', 'Growing'),
                notes              = request.form.get('notes', ''),
                image_path         = image_path,
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
                    filename        = secure_filename(file.filename)
                    filename        = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
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

    # ═════════════════════════════════════════════════════════
    #  EXPENSE ROUTES
    # ═════════════════════════════════════════════════════════

    @app.route('/expenses')
    @login_required
    def expenses():
        all_crops    = Crop.query.order_by(Crop.name).all()
        crop_id      = request.args.get('crop_id', type=int)
        query        = Expense.query
        if crop_id:
            query = query.filter_by(crop_id=crop_id)
        all_expenses = query.order_by(Expense.date.desc()).all()
        grand_total  = sum(e.total for e in all_expenses)
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

    # ── JSON helper for live total ────────────────────────────
    @app.route('/api/expense-total', methods=['POST'])
    @login_required
    def api_expense_total():
        data  = request.json or {}
        total = (float(data.get('seeds', 0)) + float(data.get('fertilizer', 0)) +
                 float(data.get('equipment', 0)) + float(data.get('labour', 0)) +
                 float(data.get('other', 0)))
        return jsonify({'total': round(total, 2)})

    # ═════════════════════════════════════════════════════════
    #  LABOUR ROUTES
    # ═════════════════════════════════════════════════════════

    @app.route('/labour')
    @login_required
    def labour():
        crop_id       = request.args.get('crop_id', type=int)
        crops         = Crop.query.order_by(Crop.name).all()
        query         = Labour.query
        if crop_id:
            query = query.filter_by(crop_id=crop_id)
        labours       = query.order_by(Labour.date.desc()).all()
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

    # ═════════════════════════════════════════════════════════
    #  HARVEST ROUTES
    # ═════════════════════════════════════════════════════════

    @app.route('/harvest')
    @login_required
    def harvest():
        crop_id          = request.args.get('crop_id', type=int)
        crops            = Crop.query.order_by(Crop.name).all()
        query            = Harvest.query
        if crop_id:
            query = query.filter_by(crop_id=crop_id)
        harvests         = query.order_by(Harvest.harvest_date.desc()).all()
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

    # ═════════════════════════════════════════════════════════
    #  PROFIT SUMMARY
    # ═════════════════════════════════════════════════════════

    @app.route('/profit')
    @login_required
    def profit():
        crops   = Crop.query.order_by(Crop.name).all()
        summary = []
        for crop in crops:
            inv = crop.total_investment
            inc = crop.total_income
            pl  = inc - inv
            summary.append({
                'crop':       crop,
                'investment': inv,
                'income':     inc,
                'profit':     pl,
                'pct':        round((pl / inv * 100) if inv else 0, 1),
            })
        grand_inv = sum(s['investment'] for s in summary)
        grand_inc = sum(s['income']     for s in summary)
        grand_pl  = grand_inc - grand_inv
        return render_template('profit.html',
                               summary=summary,
                               grand_inv=grand_inv,
                               grand_inc=grand_inc,
                               grand_pl=grand_pl)

    # ═════════════════════════════════════════════════════════
    #  REPORTS & CSV EXPORT
    # ═════════════════════════════════════════════════════════

    @app.route('/reports')
    @login_required
    def reports():
        crops = Crop.query.order_by(Crop.name).all()
        return render_template('reports.html', crops=crops)

    @app.route('/reports/export/crops')
    @login_required
    def export_crops():
        crops  = Crop.query.all()
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
                extract('year',  Expense.date) == year)
        expenses = query.order_by(Expense.date).all()
        output   = io.StringIO()
        writer   = csv.writer(output)
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

    # ═════════════════════════════════════════════════════════
    #  CROP GROWTH PHOTOS
    # ═════════════════════════════════════════════════════════

    @app.route('/crops/<int:crop_id>/photos')
    @login_required
    def crop_photos(crop_id):
        crop   = Crop.query.get_or_404(crop_id)
        photos = (CropPhoto.query
                  .filter_by(crop_id=crop_id)
                  .order_by(CropPhoto.taken_date.asc())
                  .all())
        weeks = {}
        for p in photos:
            wk = p.week_number or 0
            weeks.setdefault(wk, []).append(p)
        return render_template('crop_photos.html',
                               crop=crop, photos=photos,
                               weeks=dict(sorted(weeks.items())))

    @app.route('/crops/<int:crop_id>/photos/upload', methods=['GET', 'POST'])
    @login_required
    def crop_photo_upload(crop_id):
        crop = Crop.query.get_or_404(crop_id)

        if request.method == 'POST':
            if 'photo' not in request.files:
                flash('No file selected.', 'danger')
                return redirect(request.url)

            file = request.files['photo']
            if not file or not file.filename:
                flash('No file selected.', 'danger')
                return redirect(request.url)

            if not allowed_file(file.filename):
                flash('Only image files allowed (PNG, JPG, JPEG, GIF, WEBP).', 'danger')
                return redirect(request.url)

            ext      = file.filename.rsplit('.', 1)[1].lower()
            filename = f"crop{crop_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.{ext}"
            save_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'crop_photos')
            os.makedirs(save_dir, exist_ok=True)
            file.save(os.path.join(save_dir, filename))

            taken_date_str = request.form.get('taken_date', '')
            taken_date     = (datetime.strptime(taken_date_str, '%Y-%m-%d').date()
                              if taken_date_str else date.today())
            week_number    = max(1, ((taken_date - crop.seeding_date).days // 7) + 1)

            photo = CropPhoto(
                crop_id      = crop_id,
                photo_path   = filename,
                caption      = request.form.get('caption', '').strip(),
                week_number  = week_number,
                growth_stage = request.form.get('growth_stage', ''),
                taken_date   = taken_date,
            )
            db.session.add(photo)
            db.session.commit()
            flash(f'Photo uploaded! Week {week_number} growth recorded. 📸', 'success')
            return redirect(url_for('crop_photos', crop_id=crop_id))

        days_since_seeding = (date.today() - crop.seeding_date).days
        suggested_week     = max(1, (days_since_seeding // 7) + 1)
        return render_template('crop_photo_upload.html',
                               crop=crop,
                               suggested_week=suggested_week,
                               growth_stages=CropPhoto.GROWTH_STAGES)

    @app.route('/crops/<int:crop_id>/photos/<int:photo_id>/delete', methods=['POST'])
    @login_required
    def crop_photo_delete(crop_id, photo_id):
        photo = CropPhoto.query.get_or_404(photo_id)
        if photo.crop_id != crop_id:
            flash('Invalid request.', 'danger')
            return redirect(url_for('crop_photos', crop_id=crop_id))
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'crop_photos', photo.photo_path)
        if os.path.exists(file_path):
            os.remove(file_path)
        db.session.delete(photo)
        db.session.commit()
        flash('Photo deleted.', 'info')
        return redirect(url_for('crop_photos', crop_id=crop_id))

    @app.route('/crop-photos/all')
    @login_required
    def all_crop_photos():
        crops        = Crop.query.order_by(Crop.name).all()
        photos       = (CropPhoto.query
                        .order_by(CropPhoto.taken_date.desc())
                        .limit(50).all())
        total_photos = CropPhoto.query.count()
        return render_template('all_photos.html',
                               crops=crops,
                               photos=photos,
                               total_photos=total_photos)

    # ═════════════════════════════════════════════════════════
    #  MARKET PRICES
    # ═════════════════════════════════════════════════════════

    @app.route('/market-price')
    @login_required
    def market_price():
        all_crops     = Crop.query.order_by(Crop.name).all()
        growing_crops = Crop.query.filter_by(status='Growing').order_by(Crop.name).all()
        return render_template('market_price.html',
                               growing_crops=growing_crops,
                               all_crops=all_crops)

    # ═════════════════════════════════════════════════════════
    #  SMART FEATURE 1 — CROP RECOMMENDATION
    # ═════════════════════════════════════════════════════════

    @app.route('/crop-recommendation', methods=['GET', 'POST'])
    @login_required
    def crop_recommendation():
        season   = request.form.get('season', '')
        soil     = request.form.get('soil_type', '')
        water    = request.form.get('water_req', '')
        results  = []
        searched = False

        if request.method == 'POST' and season:
            searched = True
            q = CropRecommendation.query
            q = q.filter_by(season=season)
            if soil and soil != 'Any':
                q = q.filter_by(soil_type=soil)
            if water:
                q = q.filter_by(water_req=water)
            rows = q.all()
            # Deduplicate: keep best-profit row per crop
            seen = {}
            for r in rows:
                if r.crop_name not in seen:
                    seen[r.crop_name] = r
            results = sorted(seen.values(),
                             key=lambda x: x.expected_profit_per_acre, reverse=True)

        return render_template('crop_recommendation.html',
                               results=results, searched=searched,
                               season=season, soil=soil, water=water)

    # ═════════════════════════════════════════════════════════
    #  SMART FEATURE 2 — FERTILIZER GUIDE
    # ═════════════════════════════════════════════════════════

    @app.route('/fertilizer', methods=['GET', 'POST'])
    @login_required
    def fertilizer_recommendation():
        crop_name = request.form.get('crop_name', '')
        stage     = request.form.get('growth_stage', '')
        results   = []
        searched  = False

        all_crops = [r[0] for r in
                     db.session.query(FertilizerRecommendation.crop_name)
                     .distinct().order_by(FertilizerRecommendation.crop_name).all()]

        if request.method == 'POST' and crop_name:
            searched = True
            q = FertilizerRecommendation.query.filter_by(crop_name=crop_name)
            if stage:
                q = q.filter_by(growth_stage=stage)
            results = q.order_by(
                FertilizerRecommendation.growth_stage,
                FertilizerRecommendation.priority).all()

        stages = []
        if crop_name:
            stages = [s[0] for s in
                      db.session.query(FertilizerRecommendation.growth_stage)
                      .filter_by(crop_name=crop_name)
                      .distinct()
                      .order_by(FertilizerRecommendation.growth_stage).all()]

        return render_template('fertilizer.html',
                               results=results, searched=searched,
                               crop_name=crop_name, stage=stage,
                               all_crops=all_crops, stages=stages)

    # ═════════════════════════════════════════════════════════
    #  SMART FEATURE 3 — PEST & DISEASE CONTROL
    # ═════════════════════════════════════════════════════════

    @app.route('/pesticide', methods=['GET', 'POST'])
    @login_required
    def pesticide_recommendation():
        crop_name = request.form.get('crop_name', '')
        pest_type = request.form.get('pest_type', '')
        results   = []
        searched  = False

        all_crops = [r[0] for r in
                     db.session.query(PesticideRecommendation.crop_name)
                     .distinct().order_by(PesticideRecommendation.crop_name).all()]

        if request.method == 'POST' and crop_name:
            searched = True
            q = PesticideRecommendation.query.filter_by(crop_name=crop_name)
            if pest_type:
                q = q.filter_by(pest_type=pest_type)
            results = q.order_by(
                PesticideRecommendation.pest_type,
                PesticideRecommendation.pest_name).all()

        return render_template('pesticide.html',
                               results=results, searched=searched,
                               crop_name=crop_name, pest_type=pest_type,
                               all_crops=all_crops)

    # ═════════════════════════════════════════════════════════
    #  SMART FEATURE 4 — SEASONAL ALERTS
    # ═════════════════════════════════════════════════════════

    @app.route('/seasonal-alerts')
    @login_required
    def seasonal_alerts():
        current_month = date.today().month
        month_filter  = request.args.get('month', current_month, type=int)

        alerts = (SeasonalAlert.query
                  .filter_by(month=month_filter)
                  .order_by(SeasonalAlert.priority.desc(), SeasonalAlert.crop_name)
                  .all())

        month_names = ['', 'January', 'February', 'March', 'April', 'May', 'June',
                       'July', 'August', 'September', 'October', 'November', 'December']

        return render_template('seasonal_alerts.html',
                               alerts=alerts,
                               month_filter=month_filter,
                               month_names=month_names,
                               current_month=current_month)

    # ═════════════════════════════════════════════════════════
    #  SMART FEATURE 5 — PROFIT PREDICTOR
    # ═════════════════════════════════════════════════════════

    @app.route('/profit-prediction', methods=['GET', 'POST'])
    @login_required
    def profit_prediction():
        all_crops   = Crop.query.order_by(Crop.name).all()
        pred_crop   = request.form.get('pred_crop', '')
        pred_area   = float(request.form.get('pred_area', 0) or 0)
        prediction  = None

        if request.method == 'POST' and pred_crop and pred_area > 0:
            rec = CropRecommendation.query.filter_by(crop_name=pred_crop).first()
            if rec:
                exp_yield  = rec.avg_yield_acre * pred_area
                exp_income = exp_yield * rec.avg_price_quintal
                exp_cost   = rec.cost_per_acre * pred_area
                exp_profit = exp_income - exp_cost
                prediction = {
                    'crop':     pred_crop,
                    'area':     pred_area,
                    'yield_q':  round(exp_yield, 1),
                    'income':   round(exp_income),
                    'cost':     round(exp_cost),
                    'profit':   round(exp_profit),
                    'roi':      round((exp_profit / exp_cost * 100), 1) if exp_cost else 0,
                    'emoji':    rec.emoji,
                    'duration': rec.duration_days,
                    'price_q':  rec.avg_price_quintal,
                }

        # Chart data for actual crops
        chart_labels = []
        chart_income = []
        chart_cost   = []
        chart_profit = []
        for c in all_crops:
            if c.total_investment > 0 or c.total_income > 0:
                chart_labels.append(c.name)
                chart_income.append(round(c.total_income))
                chart_cost.append(round(c.total_investment))
                chart_profit.append(round(c.profit_loss))

        rec_crops = (db.session
                     .query(CropRecommendation.crop_name, CropRecommendation.emoji)
                     .distinct()
                     .order_by(CropRecommendation.crop_name)
                     .all())

        return render_template('profit_prediction.html',
                               all_crops=all_crops,
                               prediction=prediction,
                               pred_crop=pred_crop,
                               pred_area=pred_area,
                               chart_labels=chart_labels,
                               chart_income=chart_income,
                               chart_cost=chart_cost,
                               chart_profit=chart_profit,
                               rec_crops=rec_crops)

    # ═════════════════════════════════════════════════════════
    #  SMART FEATURE 6 — WEATHER TIPS
    # ═════════════════════════════════════════════════════════

    @app.route('/weather-suggestions')
    @login_required
    def weather_suggestions():
        growing_crops = Crop.query.filter_by(status='Growing').all()
        month         = date.today().month

        # Seasonal weather logic — no external API needed
        if month in [12, 1, 2]:
            season_label, temp, humidity, rain_chance, wind = 'Winter',      18, 62, 10, 8
        elif month in [3, 4, 5]:
            season_label, temp, humidity, rain_chance, wind = 'Summer',      36, 35,  5, 14
        elif month in [6, 7, 8, 9]:
            season_label, temp, humidity, rain_chance, wind = 'Monsoon',     29, 85, 75, 18
        else:
            season_label, temp, humidity, rain_chance, wind = 'Post-Monsoon',26, 65, 20, 10

        weather = {
            'temp': temp, 'humidity': humidity,
            'rain_chance': rain_chance, 'wind': wind,
            'season': season_label,
            'month_name': date.today().strftime('%B'),
        }

        # Per-crop suggestions
        suggestions = []
        for crop in growing_crops:
            days  = (date.today() - crop.seeding_date).days
            stage = ('Seedling'  if days < 25 else
                     'Vegetative' if days < 60 else
                     'Flowering'  if days < 90 else 'Maturity')
            tips  = []

            if rain_chance > 60:
                tips.append({'icon': '🌧️', 'color': '#3b82f6',
                    'title': 'Skip Irrigation Today',
                    'msg': f'Rain expected ({rain_chance}% chance). Skip irrigation for {crop.name} to avoid waterlogging.'})
                tips.append({'icon': '🍄', 'color': '#dc2626',
                    'title': 'Fungal Disease Risk',
                    'msg': f'High humidity ({humidity}%) + rain = fungal risk. Check {crop.name} for blight/rust symptoms.'})
            elif temp > 35:
                tips.append({'icon': '💧', 'color': '#f59e0b',
                    'title': 'Extra Irrigation Needed',
                    'msg': f'High temp ({temp}°C). Irrigate {crop.name} in evening to reduce evaporation.'})
                tips.append({'icon': '☀️', 'color': '#f97316',
                    'title': 'Heat Stress Watch',
                    'msg': f'Above 35°C can damage {crop.name} at {stage} stage. Apply potassium foliar spray.'})
            elif humidity > 80:
                tips.append({'icon': '🌫️', 'color': '#6366f1',
                    'title': 'High Humidity Alert',
                    'msg': f'Humidity {humidity}% — ideal for fungal diseases. Ensure good drainage for {crop.name}.'})
            else:
                tips.append({'icon': '✅', 'color': '#16a34a',
                    'title': 'Good Growing Conditions',
                    'msg': f'Temp {temp}°C, humidity {humidity}% — suitable for {crop.name} at {stage} stage.'})

            if stage == 'Flowering' and rain_chance > 50:
                tips.append({'icon': '🌸', 'color': '#ec4899',
                    'title': 'Flowering Stage — Rain Risk',
                    'msg': f'{crop.name} is flowering. Heavy rain can damage flowers. Avoid chemical sprays now.'})

            suggestions.append({'crop': crop, 'stage': stage, 'days': days, 'tips': tips})

        # General tips
        general_tips = []
        if rain_chance > 60:
            general_tips.append('🌧️ Rain expected — postpone fertilizer application 2-3 days.')
            general_tips.append('🚜 Do not spray pesticides before rain — it washes off immediately.')
        if temp > 35:
            general_tips.append('🌡️ Very hot — do all field work before 10 AM or after 5 PM.')
            general_tips.append('💧 Check drip/sprinkler systems for clogs in hot weather.')
        if humidity > 80:
            general_tips.append('🍄 High humidity — scout for fungal diseases every 2-3 days.')
        if wind > 15:
            general_tips.append('💨 High winds — do not spray pesticides or fertilizers today.')

        return render_template('weather_suggestions.html',
                               weather=weather,
                               suggestions=suggestions,
                               general_tips=general_tips,
                               growing_crops=growing_crops)

    # ── DB Init CLI Command ───────────────────────────────────

    @app.cli.command('init-db')
    def init_db():
        """Create all tables and seed sample data."""
        db.create_all()
        seed_sample_data(Crop, Expense, Labour, Harvest)
        print("✅  Database initialised with sample data.")

    return app


# ─────────────────────────────────────────────────────────────
#  SEED DATA
# ─────────────────────────────────────────────────────────────

def seed_sample_data(Crop, Expense, Labour, Harvest):
    """Insert sample data only on first run."""
    if Crop.query.count() > 0:
        return

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

    db.session.add_all([
        Expense(crop_id=wheat.id,  date=date(2024, 11, 1),
                seeds_cost=3500, fertilizer_cost=4200,
                equipment_cost=1500, labour_cost=2000, other_expenses=500),
        Expense(crop_id=tomato.id, date=date(2024, 9, 10),
                seeds_cost=1800, fertilizer_cost=2500,
                equipment_cost=800,  labour_cost=3000, other_expenses=300),
    ])

    db.session.add_all([
        Labour(crop_id=wheat.id,  name='Ramesh Kumar', work_type='Sowing',
               days_worked=3, payment_per_day=400, date=date(2024, 11, 2)),
        Labour(crop_id=tomato.id, name='Suresh Yadav', work_type='Harvesting',
               days_worked=5, payment_per_day=450, date=date(2024, 12, 18)),
    ])

    h = Harvest(crop_id=tomato.id, harvest_date=date(2024, 12, 20),
                total_production=2200, unit='kg', selling_price=18,
                notes='Good yield')
    h.calculate_income()
    db.session.add(h)
    db.session.commit()


# ─────────────────────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────────────────────

app = create_app()

if __name__ == '__main__':
        port = int(os.environ.get("PORT", 5000))
        app.run(host="0.0.0.0", port=port)