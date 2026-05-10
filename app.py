from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
import json

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')

db = SQLAlchemy(app)

# ─── Models ───────────────────────────────────────────────────────────────────

class Trip(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    proposals = db.relationship('Proposal', backref='trip', lazy=True, cascade='all, delete-orphan')

class Participant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    emoji = db.Column(db.String(10), default='👤')
    votes = db.relationship('Vote', backref='participant', lazy=True, cascade='all, delete-orphan')

class Proposal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey('trip.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    price_per_person = db.Column(db.Float)
    pros = db.Column(db.Text)  # JSON list
    cons = db.Column(db.Text)  # JSON list
    images = db.Column(db.Text)  # JSON list of URLs
    address = db.Column(db.String(300))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    source_url = db.Column(db.String(500))
    color = db.Column(db.String(7), default='#3B82F6')
    icon = db.Column(db.String(10), default='🏠')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    votes = db.relationship('Vote', backref='proposal', lazy=True, cascade='all, delete-orphan')

    def get_pros(self):
        try: return json.loads(self.pros) if self.pros else []
        except: return []

    def get_cons(self):
        try: return json.loads(self.cons) if self.cons else []
        except: return []

    def get_images(self):
        try: return json.loads(self.images) if self.images else []
        except: return []

    def vote_count(self):
        return Vote.query.filter_by(proposal_id=self.id).count()

class Vote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    proposal_id = db.Column(db.Integer, db.ForeignKey('proposal.id'), nullable=False)
    participant_id = db.Column(db.Integer, db.ForeignKey('participant.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('proposal_id', 'participant_id'),)


# ─── Helpers ──────────────────────────────────────────────────────────────────

COLORS = ['#EF4444','#F97316','#EAB308','#22C55E','#3B82F6','#8B5CF6','#EC4899','#14B8A6']
ICONS  = ['🏠','🏡','🏔️','🌊','🏖️','🌲','🏙️','🗺️']

def get_trip():
    return Trip.query.first()

def current_participant():
    pid = session.get('participant_id')
    if pid:
        return Participant.query.get(pid)
    return None

def is_admin():
    return session.get('is_admin', False)


# ─── Routes: Auth ─────────────────────────────────────────────────────────────

@app.route('/')
def index():
    trip = get_trip()
    participants = Participant.query.all()
    return render_template('index.html', trip=trip, participants=participants,
                           participant=current_participant(), is_admin=is_admin())

@app.route('/join', methods=['POST'])
def join():
    participant_id = request.form.get('participant_id')
    p = Participant.query.get(participant_id)
    if p:
        session['participant_id'] = p.id
        session['is_admin'] = False
    return redirect(url_for('trip_view'))

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['is_admin'] = True
            session.pop('participant_id', None)
            return redirect(url_for('admin_dashboard'))
        return render_template('admin_login.html', error=True)
    return render_template('admin_login.html', error=False)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


# ─── Routes: Trip View ────────────────────────────────────────────────────────

@app.route('/trip')
def trip_view():
    trip = get_trip()
    if not trip:
        return redirect(url_for('index'))
    participant = current_participant()
    if not participant and not is_admin():
        return redirect(url_for('index'))

    proposals = Proposal.query.filter_by(trip_id=trip.id).order_by(Proposal.created_at).all()
    participants = Participant.query.all()

    # votes dict: proposal_id -> set of participant_ids
    votes_map = {}
    for prop in proposals:
        votes_map[prop.id] = [v.participant_id for v in prop.votes]

    my_votes = set()
    if participant:
        my_votes = {v.proposal_id for v in Vote.query.filter_by(participant_id=participant.id).all()}

    return render_template('trip.html', trip=trip, proposals=proposals,
                           participants=participants, participant=participant,
                           is_admin=is_admin(), votes_map=votes_map,
                           my_votes=my_votes)


# ─── Routes: Voting ───────────────────────────────────────────────────────────

@app.route('/vote/<int:proposal_id>', methods=['POST'])
def vote(proposal_id):
    participant = current_participant()
    if not participant:
        return jsonify({'error': 'not logged in'}), 403

    existing = Vote.query.filter_by(proposal_id=proposal_id, participant_id=participant.id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        liked = False
    else:
        v = Vote(proposal_id=proposal_id, participant_id=participant.id)
        db.session.add(v)
        db.session.commit()
        liked = True

    count = Vote.query.filter_by(proposal_id=proposal_id).count()
    voters = db.session.query(Participant).join(Vote).filter(Vote.proposal_id == proposal_id).all()
    voters_html = ''.join([f'<span class="voter-badge" title="{v.name}">{v.emoji}</span>' for v in voters])

    return jsonify({'liked': liked, 'count': count, 'voters_html': voters_html})


# ─── Routes: Admin Dashboard ──────────────────────────────────────────────────

@app.route('/admin')
def admin_dashboard():
    if not is_admin():
        return redirect(url_for('admin_login'))
    trip = get_trip()
    participants = Participant.query.all()
    proposals = []
    if trip:
        proposals = Proposal.query.filter_by(trip_id=trip.id).all()
    return render_template('admin.html', trip=trip, participants=participants,
                           proposals=proposals, colors=COLORS, icons=ICONS)


# ─── Routes: Admin Trip CRUD ──────────────────────────────────────────────────

@app.route('/admin/trip/create', methods=['POST'])
def create_trip():
    if not is_admin(): return redirect(url_for('admin_login'))
    if get_trip():
        return redirect(url_for('admin_dashboard'))
    t = Trip(name=request.form['name'], description=request.form.get('description', ''))
    db.session.add(t)
    db.session.commit()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/trip/delete', methods=['POST'])
def delete_trip():
    if not is_admin(): return redirect(url_for('admin_login'))
    trip = get_trip()
    if trip:
        db.session.delete(trip)
        db.session.commit()
    return redirect(url_for('admin_dashboard'))


# ─── Routes: Admin Participants ───────────────────────────────────────────────

@app.route('/admin/participant/add', methods=['POST'])
def add_participant():
    if not is_admin(): return redirect(url_for('admin_login'))
    name = request.form.get('name', '').strip()
    emoji = request.form.get('emoji', '👤')
    if name and not Participant.query.filter_by(name=name).first():
        p = Participant(name=name, emoji=emoji)
        db.session.add(p)
        db.session.commit()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/participant/delete/<int:pid>', methods=['POST'])
def delete_participant(pid):
    if not is_admin(): return redirect(url_for('admin_login'))
    p = Participant.query.get_or_404(pid)
    db.session.delete(p)
    db.session.commit()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/participant/edit/<int:pid>', methods=['POST'])
def edit_participant(pid):
    if not is_admin(): return redirect(url_for('admin_login'))
    p = Participant.query.get_or_404(pid)
    name = request.form.get('name', '').strip()
    emoji = request.form.get('emoji', '👤').strip()
    if name:
        existing = Participant.query.filter_by(name=name).first()
        if not existing or existing.id == pid:
            p.name = name
    if emoji:
        p.emoji = emoji
    db.session.commit()
    return redirect(url_for('admin_dashboard'))


# ─── Routes: Admin Proposals ──────────────────────────────────────────────────

@app.route('/admin/proposal/add', methods=['POST'])
def add_proposal():
    if not is_admin(): return redirect(url_for('admin_login'))
    trip = get_trip()
    if not trip: return redirect(url_for('admin_dashboard'))

    pros_raw = request.form.get('pros', '')
    cons_raw = request.form.get('cons', '')
    images_raw = request.form.get('images', '')

    pros_list = [x.strip() for x in pros_raw.split('\n') if x.strip()]
    cons_list = [x.strip() for x in cons_raw.split('\n') if x.strip()]
    images_list = [x.strip() for x in images_raw.split('\n') if x.strip()]

    lat = request.form.get('latitude') or None
    lng = request.form.get('longitude') or None

    p = Proposal(
        trip_id=trip.id,
        title=request.form['title'],
        description=request.form.get('description', ''),
        price_per_person=float(request.form['price']) if request.form.get('price') else None,
        pros=json.dumps(pros_list),
        cons=json.dumps(cons_list),
        images=json.dumps(images_list),
        address=request.form.get('address', ''),
        latitude=float(lat) if lat else None,
        longitude=float(lng) if lng else None,
        source_url=request.form.get('source_url', ''),
        color=request.form.get('color', '#3B82F6'),
        icon=request.form.get('icon', '🏠'),
    )
    db.session.add(p)
    db.session.commit()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/proposal/delete/<int:pid>', methods=['POST'])
def delete_proposal(pid):
    if not is_admin(): return redirect(url_for('admin_login'))
    p = Proposal.query.get_or_404(pid)
    db.session.delete(p)
    db.session.commit()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/proposal/edit/<int:pid>', methods=['POST'])
def edit_proposal(pid):
    if not is_admin(): return redirect(url_for('admin_login'))
    p = Proposal.query.get_or_404(pid)

    pros_list = [x.strip() for x in request.form.get('pros','').split('\n') if x.strip()]
    cons_list = [x.strip() for x in request.form.get('cons','').split('\n') if x.strip()]
    images_list = [x.strip() for x in request.form.get('images','').split('\n') if x.strip()]
    lat = request.form.get('latitude') or None
    lng = request.form.get('longitude') or None

    p.title = request.form.get('title', p.title)
    p.description = request.form.get('description', '')
    p.price_per_person = float(request.form['price']) if request.form.get('price') else None
    p.pros = json.dumps(pros_list)
    p.cons = json.dumps(cons_list)
    p.images = json.dumps(images_list)
    p.address = request.form.get('address', '')
    p.latitude = float(lat) if lat else None
    p.longitude = float(lng) if lng else None
    p.source_url = request.form.get('source_url', '')
    p.color = request.form.get('color', p.color)
    p.icon = request.form.get('icon', p.icon)

    db.session.commit()
    return redirect(url_for('admin_dashboard'))


# ─── API: Live results for HTMX polling ───────────────────────────────────────

@app.route('/api/results')
def api_results():
    trip = get_trip()
    if not trip:
        return jsonify([])
    proposals = Proposal.query.filter_by(trip_id=trip.id).order_by(Proposal.created_at).all()
    participants = Participant.query.all()
    result = []
    for prop in proposals:
        voters = db.session.query(Participant).join(Vote).filter(Vote.proposal_id == prop.id).all()
        result.append({
            'id': prop.id,
            'title': prop.title,
            'count': prop.vote_count(),
            'color': prop.color,
            'icon': prop.icon,
            'voters': [{'name': v.name, 'emoji': v.emoji} for v in voters]
        })
    return jsonify(result)

@app.route('/api/proposals/map')
def api_proposals_map():
    trip = get_trip()
    if not trip:
        return jsonify([])
    proposals = Proposal.query.filter_by(trip_id=trip.id).all()
    result = []
    for p in proposals:
        if p.latitude and p.longitude:
            result.append({
                'id': p.id, 'title': p.title, 'icon': p.icon,
                'color': p.color, 'lat': p.latitude, 'lng': p.longitude,
                'address': p.address, 'price': p.price_per_person,
                'votes': p.vote_count()
            })
    return jsonify(result)


# ─── Geocoding helper ─────────────────────────────────────────────────────────

@app.route('/api/geocode')
def geocode():
    import urllib.request, urllib.parse
    address = request.args.get('address', '')
    if not address:
        return jsonify({'error': 'no address'}), 400
    url = f"https://nominatim.openstreetmap.org/search?format=json&q={urllib.parse.quote(address)}&limit=1"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'TripVote/1.0'})
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
        if data:
            return jsonify({'lat': float(data[0]['lat']), 'lng': float(data[0]['lon'])})
        return jsonify({'error': 'not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─── Init ─────────────────────────────────────────────────────────────────────

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)
