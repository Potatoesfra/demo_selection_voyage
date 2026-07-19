from flask import Flask, render_template, request, redirect, url_for, session, jsonify, make_response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import os
import json

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY')

# SameSite=None + Secure : nécessaire pour que les cookies (session Flask et
# cookie de reconnexion) survivent quand le site est chargé dans un iframe
# cross-site (ex. la démo intégrée sur le portfolio).
app.config['SESSION_COOKIE_SAMESITE'] = 'None'
app.config['SESSION_COOKIE_SECURE'] = True

# ── Database URL ───────────────────────────────────────────────────────────────
_db_url = os.environ.get('DATABASE_URL')

# Neon/Heroku fournissent parfois "postgres://" — SQLAlchemy 1.4+ exige "postgresql://"
if _db_url.startswith('postgres://'):
    _db_url = _db_url.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = _db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 300,
}

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
    emoji = db.Column(db.String(10), default='')  # vide = pas encore choisi
    votes = db.relationship('Vote', backref='participant', lazy=True, cascade='all, delete-orphan')

class Proposal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey('trip.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    price_per_person = db.Column(db.Float)
    pros = db.Column(db.Text)
    cons = db.Column(db.Text)
    images = db.Column(db.Text)
    address = db.Column(db.String(300))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    source_url = db.Column(db.String(500))
    color = db.Column(db.String(7), default='#3B82F6')
    icon = db.Column(db.String(10), default='🏠')
    travel_times = db.Column(db.Text)  # JSON: temps de trajet depuis les villes
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

    def get_travel_times(self):
        try: return json.loads(self.travel_times) if self.travel_times else {}
        except: return {}

    def vote_count(self):
        return Vote.query.filter_by(proposal_id=self.id).count()

class Vote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    proposal_id = db.Column(db.Integer, db.ForeignKey('proposal.id'), nullable=False)
    participant_id = db.Column(db.Integer, db.ForeignKey('participant.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('proposal_id', 'participant_id'),)

class Veto(db.Model):
    """Un participant peut mettre un seul véto sur une proposition."""
    id = db.Column(db.Integer, primary_key=True)
    proposal_id = db.Column(db.Integer, db.ForeignKey('proposal.id'), nullable=False)
    participant_id = db.Column(db.Integer, db.ForeignKey('participant.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('proposal_id', 'participant_id'),)


# ─── Helpers ──────────────────────────────────────────────────────────────────

COLORS = ['#EF4444','#F97316','#EAB308','#22C55E','#3B82F6','#8B5CF6','#EC4899','#14B8A6']
ICONS  = ['🏠','🏡','🏔️','🌊','🏖️','🌲','🏙️','🗺️']

COOKIE_NAME = 'tripvote_pid'
COOKIE_DAYS = 30

def get_trip():
    return Trip.query.first()

def current_participant():
    # 1. Vérifier la session Flask
    pid = session.get('participant_id')
    if pid:
        p = Participant.query.get(pid)
        if p:
            return p
    # 2. Vérifier le cookie persistant
    pid_cookie = request.cookies.get(COOKIE_NAME)
    if pid_cookie:
        try:
            p = Participant.query.get(int(pid_cookie))
            if p:
                session['participant_id'] = p.id
                session['is_admin'] = False
                return p
        except (ValueError, TypeError):
            pass
    return None

def is_admin():
    return session.get('is_admin', False)


# ─── Routes: Auth ─────────────────────────────────────────────────────────────

@app.route('/')
def index():
    # Si déjà connecté (session ou cookie), rediriger direct vers le trip
    participant = current_participant()
    if participant:
        return redirect(url_for('trip_view'))
    if is_admin():
        return redirect(url_for('admin_dashboard'))

    trip = get_trip()
    participants = Participant.query.all()
    return render_template('index.html', trip=trip, participants=participants,
                           participant=None, is_admin=False)

@app.route('/join', methods=['POST'])
def join():
    participant_id = request.form.get('participant_id')
    p = Participant.query.get(participant_id)
    if p:
        # Emoji : seulement si c'est la première connexion (emoji vide)
        if not p.emoji:
            chosen_emoji = request.form.get('chosen_emoji', '').strip()
            p.emoji = chosen_emoji if chosen_emoji else '👤'
            db.session.commit()

        session['participant_id'] = p.id
        session['is_admin'] = False

        resp = make_response(redirect(url_for('trip_view')))
        resp.set_cookie(
            COOKIE_NAME,
            str(p.id),
            max_age=int(timedelta(days=COOKIE_DAYS).total_seconds()),
            httponly=True,
            samesite='None',
            secure=True
        )
        return resp
    return redirect(url_for('index'))

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
    resp = make_response(redirect(url_for('index')))
    resp.delete_cookie(COOKIE_NAME, samesite='None', secure=True)
    return resp


@app.route('/api/check-name')
def check_name():
    """Vérifie si un nom est déjà pris et retourne les profils similaires."""
    name = request.args.get('name', '').strip().lower()
    if not name:
        return jsonify({'available': False, 'similar': []})

    participants = Participant.query.all()
    exact = None
    similar = []
    for p in participants:
        p_lower = p.name.lower()
        if p_lower == name:
            exact = {'id': p.id, 'name': p.name, 'emoji': p.emoji or '👤'}
        elif name in p_lower or p_lower in name or _similarity(name, p_lower) > 0.6:
            similar.append({'id': p.id, 'name': p.name, 'emoji': p.emoji or '👤'})

    if exact:
        return jsonify({'available': False, 'exact': exact, 'similar': similar})
    return jsonify({'available': True, 'similar': similar})

def _similarity(a, b):
    """Score de similarité simple basé sur les caractères communs."""
    if not a or not b:
        return 0
    longer = a if len(a) >= len(b) else b
    shorter = b if len(a) >= len(b) else a
    matches = sum(1 for c in shorter if c in longer)
    return matches / len(longer)

@app.route('/register', methods=['POST'])
def register():
    """Crée un nouveau profil et connecte l utilisateur directement."""
    name = request.form.get('name', '').strip()
    chosen_emoji = request.form.get('chosen_emoji', '').strip()

    if not name:
        return redirect(url_for('index'))

    # Vérification exacte (insensible à la casse)
    existing = Participant.query.filter(
        db.func.lower(Participant.name) == name.lower()
    ).first()

    if existing:
        # Nom déjà pris : reconnecter sur ce profil
        if not existing.emoji and chosen_emoji:
            existing.emoji = chosen_emoji
            db.session.commit()
        session['participant_id'] = existing.id
        session['is_admin'] = False
        resp = make_response(redirect(url_for('trip_view')))
        resp.set_cookie(COOKIE_NAME, str(existing.id),
                        max_age=int(30 * 86400),
                        httponly=True, samesite='None', secure=True)
        return resp

    # Nouveau profil
    p = Participant(name=name, emoji=chosen_emoji if chosen_emoji else '👤')
    db.session.add(p)
    db.session.commit()

    session['participant_id'] = p.id
    session['is_admin'] = False
    resp = make_response(redirect(url_for('trip_view')))
    resp.set_cookie(COOKIE_NAME, str(p.id),
                    max_age=int(30 * 86400),
                    httponly=True, samesite='None', secure=True)
    return resp

@app.route('/switch')
def switch_profile():
    """Permet de changer de profil (efface session + cookie et revient à l'écran de sélection)."""
    session.pop('participant_id', None)
    session['is_admin'] = False
    resp = make_response(redirect(url_for('index')))
    resp.delete_cookie(COOKIE_NAME)
    return resp


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

    votes_map = {}
    for prop in proposals:
        votes_map[prop.id] = [v.participant_id for v in prop.votes]

    participants_by_id = {p.id: p for p in participants}

    my_votes = set()
    if participant:
        existing_ids = {p.id for p in proposals}
        my_votes = {v.proposal_id for v in Vote.query.filter_by(participant_id=participant.id).all()
                    if v.proposal_id in existing_ids}

    vote_counts = {prop.id: len(votes_map[prop.id]) for prop in proposals}
    proposals_sorted = sorted(proposals, key=lambda p: vote_counts[p.id], reverse=True)

    # Vetos
    vetos_map = {}
    for prop in proposals:
        vetos_map[prop.id] = [v.participant_id for v in Veto.query.filter_by(proposal_id=prop.id).all()]
    veto_counts = {prop.id: len(vetos_map[prop.id]) for prop in proposals}
    my_veto_proposal_id = None
    if participant:
        my_v = Veto.query.filter_by(participant_id=participant.id).first()
        if my_v:
            my_veto_proposal_id = my_v.proposal_id

    return render_template('trip.html', trip=trip, proposals=proposals,
                           proposals_sorted=proposals_sorted,
                           participants=participants, participant=participant,
                           is_admin=is_admin(), votes_map=votes_map,
                           my_votes=my_votes, participants_by_id=participants_by_id,
                           vote_counts=vote_counts,
                           vetos_map=vetos_map, veto_counts=veto_counts,
                           my_veto_proposal_id=my_veto_proposal_id)


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
    def badge(v):
        return f'<span class="voter-badge" title="{v.name}">{v.emoji or "👤"}</span>'
    voters_html = ''.join([badge(v) for v in voters])
    return jsonify({'liked': liked, 'count': count, 'voters_html': voters_html})


# ─── Routes: Veto ─────────────────────────────────────────────────────────────

@app.route('/veto/<int:proposal_id>', methods=['POST'])
def veto(proposal_id):
    participant = current_participant()
    if not participant:
        return jsonify({'error': 'not logged in'}), 403

    existing_veto_on_this = Veto.query.filter_by(proposal_id=proposal_id, participant_id=participant.id).first()

    if existing_veto_on_this:
        # Retirer le véto de cette proposition
        db.session.delete(existing_veto_on_this)
        db.session.commit()
        vetoed = False
    else:
        # Vérifie si ce participant a déjà un véto sur une AUTRE proposition
        any_veto = Veto.query.filter_by(participant_id=participant.id).first()
        if any_veto:
            return jsonify({'error': 'already_used', 'on_proposal': any_veto.proposal_id}), 409
        # Poser le véto
        v = Veto(proposal_id=proposal_id, participant_id=participant.id)
        db.session.add(v)
        db.session.commit()
        vetoed = True

    count = Veto.query.filter_by(proposal_id=proposal_id).count()
    vetoers = db.session.query(Participant).join(Veto, Veto.participant_id == Participant.id).filter(Veto.proposal_id == proposal_id).all()
    def badge(v):
        return f'<span class="voter-badge" title="{v.name}">{v.emoji or "👤"}</span>'
    vetoers_html = ''.join([badge(v) for v in vetoers])
    return jsonify({'vetoed': vetoed, 'count': count, 'vetoers_html': vetoers_html})


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

@app.route('/admin/reset', methods=['POST'])
def reset_all():
    """Supprime absolument tout : trip, propositions, participants, votes."""
    if not is_admin(): return redirect(url_for('admin_login'))
    Vote.query.delete()
    Veto.query.delete()
    Proposal.query.delete()
    Trip.query.delete()
    Participant.query.delete()
    db.session.commit()
    return redirect(url_for('admin_dashboard'))


# ─── Routes: Admin Participants ───────────────────────────────────────────────

@app.route('/admin/participant/add', methods=['POST'])
def add_participant():
    if not is_admin(): return redirect(url_for('admin_login'))
    name = request.form.get('name', '').strip()
    # emoji vide : sera choisi par l'utilisateur à sa première connexion
    if name and not Participant.query.filter_by(name=name).first():
        p = Participant(name=name, emoji='')
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
    emoji = request.form.get('emoji', '').strip()
    if name:
        existing = Participant.query.filter_by(name=name).first()
        if not existing or existing.id == pid:
            p.name = name
    # L'admin peut vider l'emoji pour forcer un re-choix à la prochaine connexion
    p.emoji = emoji
    db.session.commit()
    return redirect(url_for('admin_dashboard'))


# ─── Routes: Admin Proposals ──────────────────────────────────────────────────

@app.route('/admin/proposal/add', methods=['POST'])
def add_proposal():
    if not is_admin(): return redirect(url_for('admin_login'))
    trip = get_trip()
    if not trip: return redirect(url_for('admin_dashboard'))

    pros_list = [x.strip() for x in request.form.get('pros', '').split('\n') if x.strip()]
    cons_list = [x.strip() for x in request.form.get('cons', '').split('\n') if x.strip()]
    images_list = [x.strip() for x in request.form.get('images', '').split('\n') if x.strip()]
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
        travel_times=request.form.get('travel_times', None),
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
    if request.form.get('travel_times'):
        p.travel_times = request.form.get('travel_times')

    db.session.commit()
    return redirect(url_for('admin_dashboard'))


# ─── API: Live results for HTMX polling ───────────────────────────────────────

@app.route('/api/results')
def api_results():
    trip = get_trip()
    if not trip:
        return jsonify([])
    proposals = Proposal.query.filter_by(trip_id=trip.id).order_by(Proposal.created_at).all()
    result = []
    for prop in proposals:
        voters = db.session.query(Participant).join(Vote).filter(Vote.proposal_id == prop.id).all()
        vetoers = db.session.query(Participant).join(Veto, Veto.participant_id == Participant.id).filter(Veto.proposal_id == prop.id).all()
        result.append({
            'id': prop.id,
            'title': prop.title,
            'count': len(voters),
            'color': prop.color,
            'icon': prop.icon,
            'voters': [{'name': v.name, 'emoji': v.emoji or '👤', 'avatar': ''} for v in voters],
            'veto_count': len(vetoers),
            'vetoers': [{'name': v.name, 'emoji': v.emoji or '👤'} for v in vetoers],
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
                'votes': len(p.votes)
            })
    return jsonify(result)


# ─── Geocoding helper ─────────────────────────────────────────────────────────

# ─── Travel Times ─────────────────────────────────────────────────────────────

CITIES = {
    'Paris':     (48.8566, 2.3522),
    'Marseille': (43.2965, 5.3698),
    'Bordeaux':  (44.8378, -0.5792),
    'Toulouse':  (43.6047, 1.4442),
}

def _osrm_drive(lat1, lon1, lat2, lon2):
    """Temps de trajet voiture via OSRM public (secondes)."""
    import urllib.request
    url = (f"http://router.project-osrm.org/route/v1/driving/"
           f"{lon1},{lat1};{lon2},{lat2}?overview=false")
    req = urllib.request.Request(url, headers={'User-Agent': 'TripVote/1.0'})
    with urllib.request.urlopen(req, timeout=8) as r:
        data = json.loads(r.read())
    if data.get('code') == 'Ok':
        return data['routes'][0]['duration']  # secondes
    return None

def _fmt_duration_range(seconds):
    """Formate en plage horaire arrondie à l'heure. Ex: 4h10 → 'Approx. 4-5h', 45min → 'Approx. 45-60 min'."""
    if seconds is None:
        return None
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    if h == 0:
        # Moins d'une heure : plage de 15 min
        lo = (m // 15) * 15
        hi = lo + 15
        return f"Approx. {lo}-{hi} min"
    else:
        return f"Approx. {h}-{h+1}h"

def _nearest_station(dest_lat, dest_lng):
    """Trouve la gare la plus proche via Nominatim avec viewbox centré sur la destination."""
    import urllib.request, urllib.parse, math

    def haversine(lat1, lng1, lat2, lng2):
        R = 6371
        dlat = math.radians(lat2 - lat1)
        dlng = math.radians(lng2 - lng1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng/2)**2
        return R * 2 * math.asin(math.sqrt(a))

    # Recherche dans un rayon progressif autour de la destination
    for radius_deg in [0.5, 1.5, 3.0]:
        bbox = (
            dest_lng - radius_deg,  # left
            dest_lat - radius_deg,  # bottom
            dest_lng + radius_deg,  # right
            dest_lat + radius_deg,  # top
        )
        url = (
            f"https://nominatim.openstreetmap.org/search"
            f"?format=json"
            f"&q=railway+station"
            f"&viewbox={bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"
            f"&bounded=1"
            f"&limit=10"
        )
        req = urllib.request.Request(url, headers={'User-Agent': 'TripVote/1.0'})
        with urllib.request.urlopen(req, timeout=6) as r:
            results = json.loads(r.read())

        if results:
            # Garder uniquement les résultats vraiment proches (type station/railway)
            best = min(results, key=lambda r: haversine(dest_lat, dest_lng, float(r['lat']), float(r['lon'])))
            name = best.get('display_name', '').split(',')[0].strip()
            dist = round(haversine(dest_lat, dest_lng, float(best['lat']), float(best['lon'])), 1)
            return name, dist

    return None, None


@app.route('/api/travel-times')
def api_travel_times():
    """Calcule les temps de trajet voiture (OSRM) + gare la plus proche depuis 4 villes."""
    try:
        dest_lat = float(request.args.get('lat'))
        dest_lng = float(request.args.get('lng'))
    except (TypeError, ValueError):
        return jsonify({'error': 'lat/lng manquant'}), 400

    # Gare la plus proche (une seule recherche pour toutes les villes)
    station_name, station_dist = None, None
    try:
        station_name, station_dist = _nearest_station(dest_lat, dest_lng)
    except Exception:
        pass

    results = {}
    for city, (clat, clng) in CITIES.items():
        drive_s = None
        try:
            drive_s = _osrm_drive(clat, clng, dest_lat, dest_lng)
        except Exception:
            pass

        results[city] = {
            'drive': _fmt_duration_range(drive_s),
            'drive_seconds': drive_s,
        }

    results['_station'] = {
        'name': station_name,
        'dist_km': station_dist,
    }

    return jsonify(results)


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
