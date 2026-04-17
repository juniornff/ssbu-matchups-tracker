from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, session
import os
from models import db, Participante, Personaje, Evento, Asistencia, Ronda, Torneo, TorneoResultado, Match, TipoUsuario, Usuario
import utils
from utils import bcrypt
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import atexit
from datetime import datetime, timedelta
import json

# =============================================================================
# Configuración de la aplicación Flask
# =============================================================================

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(app.instance_path, 'smash.db')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or utils.generar_Codigo_Secreto()
app.logger.info(f"SECRET_KEY: {app.config['SECRET_KEY']}")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# Duración de la sesión (configurable via variable de entorno SESSION_LIFETIME_HOURS, por defecto 24h)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=int(os.environ.get('SESSION_LIFETIME_HOURS', 24)))

# Asegurar que el directorio de instancias exista
os.makedirs(app.instance_path, exist_ok=True)

# =============================================================================
# Inicialización de extensiones
# =============================================================================

# Inicializar la base de datos con la app
db.init_app(app)

# Bcrypt para hashing de contraseñas
bcrypt.init_app(app)

# Flask-Login para gestión de sesiones de usuario
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # Ruta a la que redirigir si no está autenticado
login_manager.login_message = 'Por favor inicia sesión para acceder a esta página.'
login_manager.login_message_category = 'warning'


@login_manager.user_loader
def load_user(user_id):
    """
    Callback requerido por Flask-Login para recargar el usuario
    desde la BD usando el ID almacenado en la sesión.
    """
    return Usuario.query.get(int(user_id))


# Ejecutar la inicialización al importar
utils.init_db(app)

# =============================================================================
# Configuración del Scheduler (tareas programadas)
# =============================================================================

scheduler = BackgroundScheduler()
scheduler.start()

# Variables
# Nombre comunidad o liga
COMUNITY_NAME = os.environ.get('COMUNITY_NAME') or 'Jugadores de la liga'
# Variable que indica que Ronda usar para el boton en Index
ronda_actual_id = None
# Variable ajustable para el intervalo (en horas)
INTERVALO_ACTUALIZACION_HORAS = 24
# Variable para el URL del API de Torneos
API_TORNEOS_URL = os.environ.get('API_TORNEOS_URL') or 'http://tournament-server:3000'

with app.app_context():
    app.logger.info(f"Intentando Conexión con API con el URL {API_TORNEOS_URL}...")
    if utils.check_api_connection(API_TORNEOS_URL):
        app.logger.info("Conexión con API de torneos establecida correctamente.")
    else:
        app.logger.warning("No se pudo conectar con la API de torneos. Algunas funciones pueden no estar disponibles.")

# Función para la tarea programada
def actualizar_personajes_automatico():
    with app.app_context():
        try:
            app.logger.info(f"{datetime.now()}: Ejecutando actualización automática de personajes...")
            utils.actualizar_personajes_participantes_logic(app, API_TORNEOS_URL)
            app.logger.info(f"{datetime.now()}: Actualización automática de personajes completada")
        except Exception as e:
            app.logger.info(f"{datetime.now()}: Error en actualización automática: {str(e)}")

# Programar la tarea
scheduler.add_job(
    func=actualizar_personajes_automatico,
    trigger=IntervalTrigger(hours=INTERVALO_ACTUALIZACION_HORAS),
    id='actualizar_personajes_job',
    name='Actualizar personajes de participantes cada 24 horas',
    replace_existing=True)

# Apagar el scheduler cuando la aplicación se cierre
atexit.register(lambda: scheduler.shutdown())

# =============================================================================
# Filtros y Context Processors
# =============================================================================

@app.template_filter('get_attr')
def get_attr_filter(obj, attr):
    """Filtro para acceder a atributos dinámicos en plantillas Jinja"""
    return getattr(obj, attr, None)

# Context processor para hacer ronda_actual_id disponible en todas las templates
@app.context_processor
def inject_ronda_actual():
    return dict(ronda_actual_id=ronda_actual_id)

# =============================================================================
# Rutas del favicon
# =============================================================================

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

# =============================================================================
# Rutas de Autenticación
# =============================================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    """
    GET:  Muestra el formulario de login.
    POST: Valida credenciales e inicia sesión si son correctas.

    Verificaciones en orden:
    1. El email existe en la BD.
    2. La contraseña es correcta.
    3. El email está verificado (cuenta activada).
    4. La cuenta está activa (no desactivada por un admin).
    """
    # Si ya está autenticado, redirigir al index
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = 'remember' in request.form

        # Buscar usuario por email
        usuario = Usuario.query.filter_by(email=email).first()

        # Mensaje genérico para no revelar si el email existe
        if not usuario or not bcrypt.check_password_hash(usuario.password_hash, password):
            flash('Email o contraseña incorrectos.', 'danger')
            return render_template('login.html', email=email)

        # Verificar que el email esté verificado
        if not usuario.email_verificado:
            flash('Debes verificar tu email antes de iniciar sesión.', 'warning')
            return render_template('login.html', email=email)

        # Verificar que la cuenta esté activa
        if not usuario.activo:
            flash('Tu cuenta está desactivada. Contacta al administrador.', 'danger')
            return render_template('login.html', email=email)

        # Iniciar sesión
        login_user(usuario, remember=remember)
        session.permanent = True

        # Actualizar fecha de último login
        usuario.fecha_ultimo_login = datetime.now()
        db.session.commit()

        app.logger.info(f"Login exitoso: {usuario.email}")

        # Redirigir a la página que intentaba acceder, o al index
        flash('Inicio de sesión exitoso.', 'success')
        next_page = request.args.get('next')
        return redirect(next_page) if next_page else redirect(url_for('index'))

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    """
    GET:  Muestra el formulario de registro.
    POST: Valida los datos y crea la cuenta de usuario.

    El registro es abierto. Todos los usuarios nuevos son tipo 'Participante'.
    Si se proporciona un nickname, se crea y vincula un Participante.
    No se inicia sesión automáticamente: se redirige al login.

    NOTA TEMPORAL: email_verificado=True hasta implementar SMTP.
    """
    # Si ya está autenticado, redirigir al index
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        password_confirm = request.form.get('password_confirm', '')
        nickname = request.form.get('nickname', '').strip()

        # --- Validaciones de campos ---
        if not email or not password:
            flash('Email y contraseña son requeridos.', 'danger')
            return render_template('register.html', email=email, nickname=nickname)

        if len(password) < 8:
            flash('La contraseña debe tener al menos 8 caracteres.', 'danger')
            return render_template('register.html', email=email, nickname=nickname)

        if password != password_confirm:
            flash('Las contraseñas no coinciden.', 'danger')
            return render_template('register.html', email=email, nickname=nickname)

        # --- Verificar unicidad del email ---
        if Usuario.query.filter_by(email=email).first():
            flash('Este email ya está registrado.', 'danger')
            return render_template('register.html', email=email, nickname=nickname)

        # --- Verificar y crear Participante si se proporcionó nickname ---
        participante = None
        if nickname:
            if Participante.query.filter_by(nickname=nickname).first():
                flash('Este nickname ya está en uso. Elige otro o déjalo vacío.', 'danger')
                return render_template('register.html', email=email, nickname=nickname)
            participante = Participante(nickname=nickname)
            db.session.add(participante)
            db.session.flush()  # Obtener el ID antes del commit

        # Determinar tipo según si el usuario proporcionó nickname
        nombre_tipo = 'Participante' if nickname else 'Espectador'
        tipo_participante = TipoUsuario.query.filter_by(nombre=nombre_tipo).first()
        if not tipo_participante:
            app.logger.error(f"No se encontró el tipo '{nombre_tipo}' en la BD.")
            flash('Error de configuración del sistema. Contacta al administrador.', 'danger')
            db.session.rollback()
            return render_template('register.html', email=email, nickname=nickname)

        # --- Crear el usuario ---
        password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
        usuario = Usuario(
            email=email,
            password_hash=password_hash,
            tipo_id=tipo_participante.id,
            activo=True,
            # TEMPORAL: email_verificado=True hasta implementar SMTP.
            # Cuando se implemente SMTP, cambiar a False y enviar token.
            email_verificado=True,
            participante_id=participante.id if participante else None
        )
        db.session.add(usuario)
        db.session.commit()

        app.logger.info(f"Nuevo usuario registrado: {email} (tipo: {nombre_tipo})")
        flash('¡Cuenta creada exitosamente! Ya puedes iniciar sesión.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/logout')
@login_required
def logout():
    """Cierra la sesión del usuario actual y redirige al login."""
    app.logger.info(f"Logout: {current_user.email}")
    logout_user()
    flash('Sesión cerrada exitosamente.', 'success')
    return redirect(url_for('login'))

# =============================================================================
# Configuración de Usuario
# =============================================================================

@app.route('/configuracion', methods=['GET', 'POST'])
@login_required
def configuracion_usuario():
    """
    Permite al usuario modificar su email, contraseña y nickname (si tiene participante).
    """
    usuario = current_user
    error = None
    success = None

    if request.method == 'POST':
        # Determinar qué acción se está realizando (por separado para evitar conflictos)
        if 'cambiar_email' in request.form:
            nuevo_email = request.form.get('email', '').strip().lower()
            # Validación básica de formato
            if not nuevo_email or '@' not in nuevo_email or '.' not in nuevo_email:
                error = 'El email no tiene un formato válido.'
            elif nuevo_email == usuario.email:
                error = 'El nuevo email es igual al actual.'
            elif Usuario.query.filter_by(email=nuevo_email).first():
                error = 'Este email ya está registrado por otro usuario.'
            else:
                usuario.email = nuevo_email
                db.session.commit()
                success = 'Email actualizado correctamente.'

        elif 'cambiar_password' in request.form:
            current_password = request.form.get('current_password', '')
            new_password = request.form.get('new_password', '')
            confirm_password = request.form.get('confirm_password', '')

            if not bcrypt.check_password_hash(usuario.password_hash, current_password):
                error = 'La contraseña actual es incorrecta.'
            elif len(new_password) < 8:
                error = 'La nueva contraseña debe tener al menos 8 caracteres.'
            elif new_password == current_password:
                error = 'La nueva contraseña no puede ser igual a la actual.'
            elif new_password != confirm_password:
                error = 'Las nuevas contraseñas no coinciden.'
            else:
                usuario.password_hash = bcrypt.generate_password_hash(new_password).decode('utf-8')
                db.session.commit()
                success = 'Contraseña actualizada correctamente.'

        elif 'crear_nickname' in request.form:
            nuevo_nickname = request.form.get('nickname', '').strip()
            if not nuevo_nickname:
                error = 'El nickname no puede estar vacío.'
            else:
                ok, msg = utils.crear_participante_para_usuario(usuario, nuevo_nickname)
                if ok:
                    success = msg
                else:
                    error = msg
        
        elif 'cambiar_nickname' in request.form:
            nuevo_nickname = request.form.get('nickname', '').strip()
            if not nuevo_nickname:
                error = 'El nickname no puede estar vacío.'
            elif usuario.participante and usuario.participante.nickname == nuevo_nickname:
                error = 'El nuevo nickname es igual al actual.'
            else:
                # Usar función auxiliar que verifica unicidad y actualiza
                ok, msg = utils.actualizar_nickname_participante(usuario, nuevo_nickname)
                if ok:
                    success = msg
                else:
                    error = msg

        # Si hubo éxito, redirigir para evitar reenvío de formulario
        if success:
            flash(success, 'success')
            return redirect(url_for('configuracion_usuario'))
        elif error:
            flash(error, 'danger')

    return render_template('configuracion.html', usuario=usuario)

# =============================================================================
# Panel de Administración
# =============================================================================

@app.route('/admin')
@login_required
def admin_panel():
    """Panel principal de administración. Solo accesible para usuarios tipo Admin."""
    if not utils.verificar_permiso_tipo(*utils.TIPOS_ADMIN):
        flash('No tienes permisos para acceder al panel de administración.', 'danger')
        return redirect(url_for('index'))
    return render_template('admin.html')

# =============================================================================
# Administración de Tipos de Usuario
# =============================================================================

@app.route('/admin/tipos')
@login_required
def admin_tipos():
    """Listado de tipos de usuario. Solo Admin."""
    if not utils.verificar_permiso_tipo(*utils.TIPOS_ADMIN):
        return redirect(url_for('index'))
    tipos = TipoUsuario.query.order_by(TipoUsuario.id).all()
    return render_template('admin_tipos.html', tipos=tipos)


@app.route('/admin/tipos/crear', methods=['POST'])
@login_required
def admin_tipo_crear():
    """Crear un nuevo tipo de usuario. Solo Admin."""
    if not utils.verificar_permiso_tipo(*utils.TIPOS_ADMIN):
        return redirect(url_for('index'))
    nombre = request.form.get('nombre', '').strip()
    if not nombre:
        flash('El nombre del tipo no puede estar vacío.', 'danger')
        return redirect(url_for('admin_tipos'))
    if TipoUsuario.query.filter_by(nombre=nombre).first():
        flash('Ya existe un tipo con ese nombre.', 'danger')
        return redirect(url_for('admin_tipos'))
    nuevo = TipoUsuario(nombre=nombre)
    db.session.add(nuevo)
    db.session.commit()
    flash(f'Tipo "{nombre}" creado correctamente.', 'success')
    return redirect(url_for('admin_tipos'))


@app.route('/admin/tipos/editar/<int:id>', methods=['POST'])
@login_required
def admin_tipo_editar(id):
    """Editar un tipo de usuario. Solo Admin."""
    if not utils.verificar_permiso_tipo(*utils.TIPOS_ADMIN):
        return redirect(url_for('index'))
    tipo = TipoUsuario.query.get_or_404(id)
    nuevo_nombre = request.form.get('nombre', '').strip()
    if not nuevo_nombre:
        flash('El nombre no puede estar vacío.', 'danger')
        return redirect(url_for('admin_tipos'))
    if nuevo_nombre == tipo.nombre:
        flash('El nombre es el mismo que el actual.', 'warning')
        return redirect(url_for('admin_tipos'))
    otro = TipoUsuario.query.filter(TipoUsuario.nombre == nuevo_nombre, TipoUsuario.id != id).first()
    if otro:
        flash('Ya existe otro tipo con ese nombre.', 'danger')
        return redirect(url_for('admin_tipos'))
    tipo.nombre = nuevo_nombre
    db.session.commit()
    flash(f'Tipo actualizado a "{nuevo_nombre}".', 'success')
    return redirect(url_for('admin_tipos'))


@app.route('/admin/tipos/eliminar/<int:id>', methods=['POST'])
@login_required
def admin_tipo_eliminar(id):
    """Eliminar un tipo de usuario. Solo Admin. No se puede eliminar si hay usuarios con ese tipo."""
    if not utils.verificar_permiso_tipo(*utils.TIPOS_ADMIN):
        return redirect(url_for('index'))
    tipo = TipoUsuario.query.get_or_404(id)
    # Verificar si hay usuarios asociados
    usuarios_con_tipo = Usuario.query.filter_by(tipo_id=tipo.id).count()
    if usuarios_con_tipo > 0:
        flash(f'No se puede eliminar el tipo "{tipo.nombre}" porque hay {usuarios_con_tipo} usuario(s) que lo tienen asignado.', 'danger')
        return redirect(url_for('admin_tipos'))
    db.session.delete(tipo)
    db.session.commit()
    flash(f'Tipo "{tipo.nombre}" eliminado correctamente.', 'success')
    return redirect(url_for('admin_tipos'))

# =============================================================================
# Administración de Usuarios
# =============================================================================

@app.route('/admin/usuarios')
@login_required
def admin_usuarios():
    """Listado de usuarios. Solo Admin."""
    if not utils.verificar_permiso_tipo(*utils.TIPOS_ADMIN):
        return redirect(url_for('index'))
    usuarios = Usuario.query.order_by(Usuario.id).all()
    return render_template('admin_usuarios.html', usuarios=usuarios)


@app.route('/admin/usuarios/toggle/<int:id>', methods=['POST'])
@login_required
def admin_usuario_toggle(id):
    """Activar/desactivar un usuario. Solo Admin."""
    if not utils.verificar_permiso_tipo(*utils.TIPOS_ADMIN):
        return redirect(url_for('index'))
    usuario = Usuario.query.get_or_404(id)
    # No permitir desactivar al propio admin
    if usuario.id == current_user.id:
        flash('No puedes desactivar tu propia cuenta.', 'danger')
        return redirect(url_for('admin_usuarios'))
    
    # Si se intenta desactivar un Admin, verificar que no sea el único activo
    if usuario.tipo.nombre == 'Admin' and usuario.activo:
        # Contar otros admins activos (excluyendo este usuario)
        otros_admins_activos = Usuario.query.filter(
            Usuario.tipo.has(nombre='Admin'),
            Usuario.id != usuario.id,
            Usuario.activo == True
        ).count()
        if otros_admins_activos == 0:
            flash('No se puede desactivar al único administrador activo del sistema.', 'danger')
            return redirect(url_for('admin_usuarios'))
    
    usuario.activo = not usuario.activo
    db.session.commit()
    estado = "activado" if usuario.activo else "desactivado"
    flash(f'Usuario {usuario.email} {estado} correctamente.', 'success')
    return redirect(url_for('admin_usuarios'))


@app.route('/admin/usuarios/eliminar/<int:id>', methods=['POST'])
@login_required
def admin_usuario_eliminar(id):
    """Eliminar un usuario. Solo Admin. No se puede eliminar si tiene participante asociado o es el único Admin."""
    if not utils.verificar_permiso_tipo(*utils.TIPOS_ADMIN):
        return redirect(url_for('index'))
    
    delete_participant = 'delete_participant' in request.form   # Checkbox
    ok, msg = utils.eliminar_usuario(
        usuario_id=id,
        delete_participant=delete_participant,
        current_user_id=current_user.id
    )
    flash(msg, 'success' if ok else 'danger')
    return redirect(url_for('admin_usuarios'))

# =============================================================================
# Administración de Usuarios - Crear y Editar
# =============================================================================

@app.route('/admin/usuarios/nuevo', methods=['GET', 'POST'])
@login_required
def admin_usuario_nuevo():
    """Formulario para crear un nuevo usuario. Solo Admin."""
    if not utils.verificar_permiso_tipo(*utils.TIPOS_ADMIN):
        return redirect(url_for('index'))

    if request.method == 'POST':
        return _guardar_usuario(request.form, crear=True)
    # GET: mostrar formulario vacío
    participantes = Participante.query.order_by(Participante.nickname).all()
    tipos = TipoUsuario.query.order_by(TipoUsuario.id).all()
    return render_template('admin_usuario_form.html', 
                           modo='crear', 
                           participantes=participantes, 
                           tipos=tipos)


@app.route('/admin/usuarios/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def admin_usuario_editar(id):
    """Formulario para editar un usuario existente. Solo Admin."""
    if not utils.verificar_permiso_tipo(*utils.TIPOS_ADMIN):
        return redirect(url_for('index'))

    usuario = Usuario.query.get_or_404(id)
    if request.method == 'POST':
        return _guardar_usuario(request.form, crear=False, usuario=usuario)

    # GET: mostrar formulario con datos del usuario
    participantes = Participante.query.order_by(Participante.nickname).all()
    tipos = TipoUsuario.query.order_by(TipoUsuario.id).all()
    return render_template('admin_usuario_form.html',
                           modo='editar',
                           usuario=usuario,
                           participantes=participantes,
                           tipos=tipos)


def _guardar_usuario(form, crear, usuario=None):
    """
    Función auxiliar para guardar (crear o editar) un usuario.
    Valida los campos y gestiona la asociación con participante.
    """
    email = form.get('email', '').strip().lower()
    tipo_id = form.get('tipo_id')
    password = form.get('password', '')
    # Participante: puede ser seleccionado de existentes o nuevo
    participante_id = form.get('participante_id')
    nuevo_nickname = form.get('nuevo_nickname', '').strip()

    # Validaciones comunes
    if not email:
        flash('El email es obligatorio.', 'danger')
        return redirect(request.referrer or url_for('admin_usuarios'))
    if '@' not in email or '.' not in email:
        flash('El email no tiene un formato válido.', 'danger')
        return redirect(request.referrer or url_for('admin_usuarios'))
    if not tipo_id or not TipoUsuario.query.get(tipo_id):
        flash('Debes seleccionar un tipo de usuario válido.', 'danger')
        return redirect(request.referrer or url_for('admin_usuarios'))

    # Validar unicidad del email (excepto si se está editando el mismo usuario)
    otro = Usuario.query.filter(Usuario.email == email)
    if not crear and usuario:
        otro = otro.filter(Usuario.id != usuario.id)
    if otro.first():
        flash('Ya existe un usuario con ese email.', 'danger')
        return redirect(request.referrer or url_for('admin_usuarios'))

    # Manejo del participante
    participante = None
    if participante_id:
        participante = Participante.query.get(participante_id)
        if not participante:
            flash('El participante seleccionado no existe.', 'danger')
            return redirect(request.referrer or url_for('admin_usuarios'))
    elif nuevo_nickname:
        # Verificar que el nickname no exista ya
        if Participante.query.filter_by(nickname=nuevo_nickname).first():
            flash(f'El nickname "{nuevo_nickname}" ya está en uso.', 'danger')
            return redirect(request.referrer or url_for('admin_usuarios'))
        participante = Participante(nickname=nuevo_nickname)
        db.session.add(participante)
        db.session.flush()  # para obtener el id

    if crear:
        # Validar contraseña obligatoria
        if not password or len(password) < 8:
            flash('La contraseña debe tener al menos 8 caracteres.', 'danger')
            return redirect(request.referrer or url_for('admin_usuarios'))
        password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
        nuevo_usuario = Usuario(
            email=email,
            password_hash=password_hash,
            tipo_id=int(tipo_id),
            activo=True,
            email_verificado=True,  # SMTP aún no implementado
            participante_id=participante.id if participante else None
        )
        db.session.add(nuevo_usuario)
        db.session.commit()
        flash(f'Usuario {email} creado correctamente.', 'success')
    else:
        # Edición: actualizar campos
        if password:
            if len(password) < 8:
                flash('La nueva contraseña debe tener al menos 8 caracteres.', 'danger')
                return redirect(request.referrer or url_for('admin_usuarios'))
            usuario.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
        usuario.email = email
        usuario.tipo_id = int(tipo_id)
        usuario.participante_id = participante.id if participante else None
        db.session.commit()
        flash(f'Usuario {email} actualizado correctamente.', 'success')

    return redirect(url_for('admin_usuarios'))

# =============================================================================
# Index
# =============================================================================

@app.route('/')
def index():
    global ronda_actual_id

    # Si no hay ronda actual configurada, obtener la última ronda creada
    if ronda_actual_id is None:
        ultima_ronda = Ronda.query.order_by(Ronda.id.desc()).first()
        # ultima_ronda = Ronda.query.join(Evento).filter(Evento.activo == True).order_by(Ronda.id.desc()).first()
        if ultima_ronda:
            ronda_actual_id = ultima_ronda.id

    # Obtener todos los eventos con sus rondas para el modal
    eventos = Evento.query.order_by(Evento.fecha.desc()).all()
    # eventos = Evento.query.filter(Evento.activo == True).order_by(Evento.fecha.desc()).all()

    return render_template('index.html',
                         ronda_actual_id=ronda_actual_id,
                         eventos=eventos,
                         comunity_name=COMUNITY_NAME)

# Configurar Ronda Actual en Index
@app.route('/configurar_ronda_actual', methods=['POST'])
def configurar_ronda_actual():
    """
    Configura la ronda actual para acceso rápido desde el Index.

    No requiere autenticación obligatoria, pero solo usuarios con tipo
    Admin o Líder de liga pueden realizar la acción.
    """
    global ronda_actual_id

    # Verificar permiso sin requerir login obligatorio en la ruta
    if not utils.verificar_permiso_tipo(*utils.TIPOS_ADMIN_LIDER):
        return redirect(url_for('index'))

    # Verificar que la ronda existe
    ronda_id = request.form.get('ronda_id')
    ronda = Ronda.query.get(ronda_id)
    if not ronda:
        flash('Ronda no encontrada', 'danger')
        return redirect(url_for('index'))

    ronda_actual_id = ronda_id
    flash('Ronda actual configurada correctamente!', 'success')
    return redirect(url_for('index'))

# =============================================================================
# Participantes
# =============================================================================

# Index Participantes
@app.route('/admin/participantes', methods=['GET', 'POST'])
@login_required
def gestion_participantes():

    # Verificar que solo Admin puede acceder a esta sección (GET y POST)
    if not utils.verificar_permiso_tipo(*utils.TIPOS_ADMIN):
        return redirect(url_for('index'))

    if request.method == 'POST':
        nickname = request.form['nickname']

        # Verificar si el nickname ya existe
        if Participante.query.filter_by(nickname=nickname).first():
            flash('Este nickname ya está registrado!', 'danger')
            return redirect(url_for('gestion_participantes'))

        nuevo = Participante(nickname=nickname)
        db.session.add(nuevo)
        db.session.commit()
        flash('Participante creado!', 'success')
        return redirect(url_for('gestion_participantes'))

    participantes = Participante.query.order_by(Participante.activo.desc(), Participante.nickname).all()
    personajes = Personaje.query.all()
    return render_template('participantes.html',
                          participantes=participantes,
                          personajes=personajes,
                          INTERVALO_ACTUALIZACION_HORAS=INTERVALO_ACTUALIZACION_HORAS)

# Actualizar participantes
@app.route('/admin/participante/actualizar', methods=['POST'])
@login_required
def actualizar_participante():
    """Actualizar nickname de un participante. Solo Admin."""
    if not utils.verificar_permiso_tipo(*utils.TIPOS_ADMIN):
        return redirect(url_for('index'))

    participante_id = request.form.get('id')
    nuevo_nickname = request.form.get('nickname')

    if not participante_id or not nuevo_nickname:
        flash('Datos incompletos', 'danger')
        return redirect(url_for('gestion_participantes'))

    participante = Participante.query.get_or_404(participante_id)

    # Verificar si el nickname ya existe (excluyendo el actual)
    otro = Participante.query.filter(Participante.nickname == nuevo_nickname, Participante.id != participante_id).first()
    if otro:
        flash('Este nickname ya está registrado!', 'danger')
        return redirect(url_for('gestion_participantes'))

    participante.nickname = nuevo_nickname
    db.session.commit()
    flash('Participante actualizado!', 'success')
    return redirect(url_for('gestion_participantes'))

# Actualizar personajes de participantes
@app.route('/admin/participantes/actualizar_personajes', methods=['POST'])
@login_required
def actualizar_personajes_participantes():
    """Actualiza los personajes de todos los participantes. Solo Admin."""
    if not utils.verificar_permiso_tipo(*utils.TIPOS_ADMIN):
        return redirect(url_for('index'))

    # Obtener todos los participantes
    try:
        app.logger.info("Ejecutando actualización de personajes")
        utils.actualizar_personajes_participantes_logic(app, API_TORNEOS_URL)
        app.logger.info('Personajes de participantes actualizados correctamente')
        flash('Personajes de participantes actualizados correctamente', 'success')
    except Exception as e:
        app.logger.info(f'Error al actualizar personajes: {str(e)}')
        flash(f'Error al actualizar personajes', 'danger')

    return redirect(url_for('gestion_participantes'))

# Retirar/Reactivar participante
@app.route('/admin/participante/toggle/<int:id>', methods=['POST'])
@login_required
def toggle_participante(id):
    """Alternar estado activo/inactivo de un participante. Solo Admin."""
    if not utils.verificar_permiso_tipo(*utils.TIPOS_ADMIN):
        return redirect(url_for('index'))
    
    participante = Participante.query.get_or_404(id)

    # Alternar estado activo/inactivo
    participante.activo = not participante.activo
    db.session.commit()

    if participante.activo:
        flash('Participante reactivado', 'success')
    else:
        flash('Participante marcado como retirado', 'success')

    return redirect(url_for('gestion_participantes'))

# Eliminar participante permanentemente
@app.route('/admin/participante/borrar/<int:id>', methods=['POST'])
@login_required
def borrar_participante(id):
    """Eliminar permanentemente un participante si no tiene relaciones. Solo Admin."""
    if not utils.verificar_permiso_tipo(*utils.TIPOS_ADMIN):
        return redirect(url_for('index'))

    ok, msg = utils.eliminar_participante(id)
    flash(msg, 'success' if ok else 'danger')
    return redirect(url_for('gestion_participantes'))

# =============================================================================
# Personajes
# =============================================================================

# Index Personajes
@app.route('/admin/personajes', methods=['GET', 'POST'])
@login_required
def gestion_personajes():
    if not utils.verificar_permiso_tipo(*utils.TIPOS_ADMIN):
        return redirect(url_for('index'))

    if request.method == 'POST':
        # Crear nuevo personaje
        nombre = request.form['nombre']

        # Verificar si ya existe
        if Personaje.query.filter_by(nombre=nombre).first():
            flash('Este personaje ya existe!', 'danger')
            return redirect(url_for('gestion_personajes'))

        nuevo = Personaje(nombre=nombre)
        db.session.add(nuevo)
        db.session.commit()
        flash('Personaje creado!', 'success')
        return redirect(url_for('gestion_personajes'))

    personajes = Personaje.query.order_by(Personaje.nombre).all()
    return render_template('personajes.html', personajes=personajes)

# Editar nombre Personaje
@app.route('/admin/personaje/editar/<int:id>', methods=['POST'])
@login_required
def editar_personaje(id):
    """Editar nombre de un personaje. Solo Admin."""
    if not utils.verificar_permiso_tipo(*utils.TIPOS_ADMIN):
        return redirect(url_for('index'))
    
    personaje = Personaje.query.get_or_404(id)
    nuevo_nombre = request.form.get('nombre')

    if not nuevo_nombre:
        flash('El nombre no puede estar vacío', 'danger')
        return redirect(url_for('gestion_personajes'))

    # Verificar si el nuevo nombre ya existe (excluyendo el actual)
    otro = Personaje.query.filter(Personaje.nombre == nuevo_nombre, Personaje.id != id).first()
    if otro:
        flash('Este nombre ya está registrado!', 'danger')
        return redirect(url_for('gestion_personajes'))

    personaje.nombre = nuevo_nombre
    db.session.commit()
    flash('Personaje actualizado!', 'success')
    return redirect(url_for('gestion_personajes'))

# Borrar Personaje
@app.route('/admin/personaje/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar_personaje(id):
    """Eliminar un personaje si no está en uso. Solo Admin."""
    if not utils.verificar_permiso_tipo(*utils.TIPOS_ADMIN):
        return redirect(url_for('index'))

    ok, msg = utils.eliminar_personaje(id, API_TORNEOS_URL)
    flash(msg, 'success' if ok else 'danger')
    return redirect(url_for('gestion_personajes'))

# =============================================================================
# Eventos
# =============================================================================

# Index Evento
@app.route('/eventos', methods=['GET', 'POST'])
@login_required
def gestion_eventos():
    if request.method == 'POST':
        
        if not utils.verificar_permiso_tipo(*utils.TIPOS_ADMIN_LIDER):
            return redirect(url_for('gestion_eventos'))

        fecha = datetime.strptime(request.form['fecha'], '%Y-%m-%d').date()
        nuevo_evento = Evento(fecha=fecha)
        db.session.add(nuevo_evento)
        db.session.commit()
        flash('Evento creado!', 'success')
        return redirect(url_for('gestion_eventos'))

    eventos = Evento.query.order_by(Evento.fecha.desc()).all()
    return render_template('eventos.html', eventos=eventos)

# Evento - Asistencia
@app.route('/evento/asistencia/<int:evento_id>', methods=['GET', 'POST'])
@login_required
def registrar_asistencia(evento_id):
    evento = Evento.query.get_or_404(evento_id)

    if request.method == 'POST':

        if not utils.verificar_permiso_tipo(*utils.TIPOS_ADMIN_LIDER):
            return redirect(url_for('registrar_asistencia', evento_id=evento_id))

        # Comprobar si el evento esta activo
        if not evento.activo:
            flash('Evento bloqueado, la asistencia no se puede modificar', 'danger')
            return redirect(url_for('registrar_asistencia', evento_id=evento_id))

        # Obtener lista de asistentes del formulario
        nuevos_asistentes_ids = request.form.getlist('asistentes')

        # Convertir a enteros
        nuevos_asistentes_ids = [int(pid) for pid in nuevos_asistentes_ids]

        # Obtener asistencias actuales del evento
        asistencias_actuales = {a.participante_id: a for a in evento.asistencias}

        # Obtener todos los participantes para verificar su estado
        todos_participantes = Participante.query.all()

        # Procesar cada participante
        for participante in todos_participantes:
            esta_presente = participante.id in nuevos_asistentes_ids
            tenia_asistencia = participante.id in asistencias_actuales

            # Solo modificar asistencias de participantes activos
            if participante.activo:
                if esta_presente and not tenia_asistencia:
                    # Añadir nueva asistencia
                    asistencia = Asistencia(evento_id=evento_id, participante_id=participante.id)
                    app.logger.info(f'{participante.nickname}:')
                    app.logger.info(f'    Ahora esta Presente')
                    db.session.add(asistencia)
                elif not esta_presente and tenia_asistencia:
                    # Eliminar asistencia existente
                    app.logger.info(f'{participante.nickname}:')
                    app.logger.info(f'    Ahora esta Ausente')
                    db.session.delete(asistencias_actuales[participante.id])
                if esta_presente:
                    app.logger.info(f'{participante.nickname}:')
                    app.logger.info(f'    Esta Presente')
                else:
                    app.logger.info(f'{participante.nickname}:')
                    app.logger.info(f'    Esta Ausente')
            else:
                if esta_presente and not tenia_asistencia:
                    app.logger.info(f'{participante.nickname}(Retirado):')
                    app.logger.info(f'    Quiso estar Presente, NEGADO')
                elif not esta_presente and tenia_asistencia:
                    app.logger.info(f'{participante.nickname}(Retirado):')
                    app.logger.info(f'    Quiso estar Ausente, NEGADO')

        db.session.commit()
        flash('Asistencia registrada!', 'success')

        # Actualizar todas las rondas del evento
        for ronda in evento.rondas:
            utils.refrescar_matches_ronda(ronda)  # Se ejecuta por cada ronda

        return redirect(url_for('registrar_asistencia', evento_id=evento_id))

    participantes = Participante.query.all()
    asistentes_ids = [a.participante_id for a in evento.asistencias]
    return render_template('asistencia.html',
                          evento=evento,
                          participantes=participantes,
                          asistentes_ids=asistentes_ids)

# Activar/Desactivar Evento
@app.route('/evento/activar_desactivar/<int:id>', methods=['POST'])
@login_required
def activar_desactivar_evento(id):
    if not utils.verificar_permiso_tipo(*utils.TIPOS_ADMIN_LIDER):
        return redirect(url_for('gestion_eventos'))

    evento = Evento.query.get_or_404(id)

    # Cambiar el estado activo/inactivo
    evento.activo = not evento.activo
    db.session.commit()

    if evento.activo:
        flash('Evento desbloqueado correctamente', 'success')
    else:
        flash('Evento bloqueado correctamente', 'success')

    return redirect(url_for('gestion_eventos'))

# Eliminar Evento
@app.route('/evento/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar_evento(id):
    if not utils.verificar_permiso_tipo(*utils.TIPOS_ADMIN_LIDER):
        return redirect(url_for('gestion_eventos'))

    evento = Evento.query.get_or_404(id)

    # Comprobar si el evento esta activo
    if not evento.activo:
        flash('Evento bloqueado, No se puede eliminar', 'danger')
        return redirect(url_for('gestion_eventos'))

    try:
        # Eliminar rondas asociadas y sus matches
        for ronda in evento.rondas:
            # Eliminar matches de la ronda
            Match.query.filter_by(ronda_id=ronda.id).delete()
            # Eliminar la ronda
            db.session.delete(ronda)
        
        # Eliminar torneos asociados al evento
        for torneo in evento.torneos:
            # Eliminar resultados del torneo en BD
            TorneoResultado.query.filter_by(torneo_id=torneo.id).delete()
            # Eliminar el torneo en la API
            resp = utils.api_request('DELETE', f"{API_TORNEOS_URL}/stages/{torneo.torneo_id_externo}")
            if 'error' in resp:
                flash(f"Error al eliminar torneo '{torneo.nombre}' en la API: {resp['error']}", 'danger')
                db.session.rollback()
                return redirect(url_for('gestion_eventos'))
            # Eliminar el torneo de la BD
            db.session.delete(torneo)

        # Eliminar asistencias del evento
        Asistencia.query.filter_by(evento_id=id).delete()

        # Eliminar el evento
        db.session.delete(evento)
        db.session.commit()
        flash('Evento eliminado con éxito', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar evento: {str(e)}', 'danger')

    return redirect(url_for('gestion_eventos'))

# =============================================================================
# Rondas
# =============================================================================

# Index Rondas
@app.route('/evento/rondas/<int:evento_id>', methods=['GET', 'POST'])
@login_required
def gestion_rondas(evento_id):
    evento = Evento.query.get_or_404(evento_id)

    if request.method == 'POST':
        if not utils.verificar_permiso_tipo(*utils.TIPOS_ADMIN_LIDER):
            return redirect(url_for('gestion_rondas', evento_id=evento_id))

        # Comprobar si el evento esta activo
        if not evento.activo:
            flash('Evento bloqueado, No se pueden crear nuevas rondas', 'danger')
            return redirect(url_for('gestion_rondas', evento_id=evento_id))

        nombre = request.form['nombre']
        nuevo_ronda = Ronda(nombre=nombre, evento_id=evento_id)
        db.session.add(nuevo_ronda)
        db.session.commit()

        # Acutalizar ronda acual
        global ronda_actual_id
        ronda_actual_id = nuevo_ronda.id
        flash('Ronda creada!', 'success')

        # Generar matches automáticamente si hay asistentes
        asistentes_ids = [a.participante_id for a in evento.asistencias]
        if asistentes_ids:
            matches_data = utils.generar_round_robin(asistentes_ids)
            for match in matches_data:
                nuevo_match = Match(
                    ronda_id=nuevo_ronda.id,
                    jugador1_id=match['jugador1_id'],
                    jugador2_id=match['jugador2_id']
                )
                db.session.add(nuevo_match)
            db.session.commit()

        return redirect(url_for('gestion_rondas', evento_id=evento_id))


    # Calcular partidas realizadas y detalles para cada ronda
    for ronda in evento.rondas:
        # Obtener matches realizadas (donde hay un ganador del match)
        realizadas = Match.query.filter(
            Match.ronda_id == ronda.id,
            Match.ganador_match != None
        ).all()

        ronda.realizadas = len(realizadas)

        # Preparar lista de realizadas para mostrar
        ronda.lista_realizadas = []
        for match in realizadas:
            jugador1 = Participante.query.get(match.jugador1_id).nickname
            jugador2 = Participante.query.get(match.jugador2_id).nickname

            # Contar victorias por jugador en las rondas
            victorias_j1 = 0
            victorias_j2 = 0
            # Lista de los campos ganador_r1 a ganador_r5
            ganadores = [
                match.ganador_r1, match.ganador_r2, match.ganador_r3,
                match.ganador_r4, match.ganador_r5
            ]
            for ganador in ganadores:
                if ganador == match.jugador1_id:
                    victorias_j1 += 1
                elif ganador == match.jugador2_id:
                    victorias_j2 += 1

            ronda.lista_realizadas.append(f"{jugador1} {victorias_j1} vs {victorias_j2} {jugador2}")

    # Calcular partidas pendientes y detalles para cada ronda
    for ronda in evento.rondas:
        # Obtener matches pendientes (sin ganador del match)
        pendientes = Match.query.filter(
            Match.ronda_id == ronda.id,
            Match.ganador_match == None
        ).all()

        ronda.pendientes = len(pendientes)

        # Preparar lista de pendientes para mostrar
        ronda.lista_pendientes = []
        for match in pendientes:
            jugador1 = Participante.query.get(match.jugador1_id).nickname
            jugador2 = Participante.query.get(match.jugador2_id).nickname
            ronda.lista_pendientes.append(f"{jugador1} vs {jugador2}")

    return render_template('rondas.html', evento=evento)

# Renombrar Ronda
@app.route('/evento/ronda/editar/<int:id>', methods=['POST'])
@login_required
def editar_ronda(id):
    ronda = Ronda.query.get_or_404(id)
    if not utils.verificar_permiso_tipo(*utils.TIPOS_ADMIN_LIDER):
        return redirect(url_for('gestion_rondas', evento_id=ronda.evento_id))

    # Comprobar si el evento esta activo
    evento = Evento.query.get(ronda.evento_id)
    if not evento.activo:
        flash('Evento bloqueado, No se pueden editar las rondas', 'danger')
        return redirect(url_for('gestion_rondas', evento_id=ronda.evento_id))

    nuevo_nombre = request.form.get('nombre')
    if nuevo_nombre:
        ronda.nombre = nuevo_nombre
        db.session.commit()
        flash('Nombre de la ronda actualizado!', 'success')
    return redirect(url_for('gestion_rondas', evento_id=ronda.evento_id))

# Eliminar Ronda
@app.route('/evento/ronda/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar_ronda(id):
    ronda = Ronda.query.get_or_404(id)
    
    if not utils.verificar_permiso_tipo(*utils.TIPOS_ADMIN_LIDER):
        return redirect(url_for('gestion_rondas', evento_id=ronda.evento_id))

    # Comprobar si el evento esta activo
    evento = Evento.query.get(ronda.evento_id)
    if not evento.activo:
        flash('Evento bloqueado, No se pueden eliminar las rondas', 'danger')
        return redirect(url_for('gestion_rondas', evento_id=evento.id))

    # Eliminar todos los matches de la ronda
    Match.query.filter_by(ronda_id=id).delete()
    # Eliminar la Ronda
    db.session.delete(ronda)
    db.session.commit()
    flash('Ronda eliminada!', 'success')
    return redirect(url_for('gestion_rondas', evento_id=evento.id))

# =============================================================================
# Matchups
# =============================================================================

# Index Matchups
@app.route('/evento/ronda/matchups/<int:ronda_id>', methods=['GET', 'POST'])
@login_required
def gestion_matchups(ronda_id):
    ronda = Ronda.query.get_or_404(ronda_id)
    todos_personajes = Personaje.query.order_by(Personaje.nombre).all()

    if request.method == 'POST':
        if not utils.verificar_permiso_tipo(*utils.TIPOS_TODOS_AUTENTICADOS):
            return redirect(url_for('gestion_matchups', ronda_id=ronda_id))

        # Comprobar si el evento esta activo
        evento = Evento.query.get(ronda.evento_id)
        if not evento.activo:
            flash('Evento bloqueado, No se pueden modificar los matchups', 'danger')
            return redirect(url_for('gestion_matchups', ronda_id=ronda.id))

        # Imprimir todos los datos del formulario para depuración
        app.logger.info("=== DATOS DEL FORMULARIO RECIBIDOS ===")
        for key, value in request.form.items():
            app.logger.info(f"  {key}: {value}")
        app.logger.info("======================================")

        # Confirmar que se envia un ID
        match_id = request.form.get('match_id')
        if not match_id:
            flash("No se especificó el match", "danger")
            return redirect(url_for('gestion_matchups', ronda_id=ronda_id))

        # Confirmar que ese ID pertenece a los Match
        match = Match.query.get(match_id)
        if not match:
            flash("Match no encontrado", "danger")
            return redirect(url_for('gestion_matchups', ronda_id=ronda_id))

        # Verificar que el match pertenece a la ronda actual
        if match.ronda_id != ronda_id:
            flash("Este match no pertenece a la ronda actual", "danger")
            return redirect(url_for('gestion_matchups', ronda_id=ronda_id))

        # Obtener videos
        videos = request.form.get('videos', '').strip()

        # Obtener el orden de los jugadores
        jugador1_id_form = int(request.form.get('jugador1_id'))
        jugador2_id_form = int(request.form.get('jugador2_id'))
        orden_coincide = (match.jugador1_id == jugador1_id_form and
                          match.jugador2_id == jugador2_id_form)

        # Verificar que los jugadores están en la asistencia del evento
        asistentes_ids = [a.participante_id for a in ronda.evento.asistencias]
        if jugador1_id_form not in asistentes_ids:
            flash("Jugador 1 no está registrado en la asistencia de este evento", "danger")
            return redirect(url_for('gestion_matchups', ronda_id=ronda_id))
        if jugador2_id_form not in asistentes_ids:
            flash("Jugador 2 no está registrado en la asistencia de este evento", "danger")
            return redirect(url_for('gestion_matchups', ronda_id=ronda_id))

        # Inicializar contadores de victorias
        victorias_j1 = 0
        victorias_j2 = 0

        # Procesar cada ronda (1-5)
        for ronda_num in range(1, 6):
            # Obtener personajes y ganador de la ronda
            personaje1_id = request.form.get(f'personaje1r{ronda_num}', '')
            personaje2_id = request.form.get(f'personaje2r{ronda_num}', '')
            ganador_id = request.form.get(f'ganador_r{ronda_num}', '')

            # Debug: imprimir valores recibidos
            app.logger.info(f"Ronda {ronda_num}:")
            app.logger.info(f"    Personaje 1: {personaje1_id}")
            app.logger.info(f"    Personaje 2: {personaje2_id}")
            app.logger.info(f"    Ganador: {ganador_id}")

            # Convertir a entero o None
            personaje1_id = int(personaje1_id) if personaje1_id and personaje1_id != 'None' and personaje1_id != '' else None
            personaje2_id = int(personaje2_id) if personaje2_id and personaje2_id != 'None' and personaje2_id != '' else None
            ganador_id = int(ganador_id) if ganador_id and ganador_id != 'None' and ganador_id != '' else None

            # Verificar que los personajes existen en la base de datos
            if personaje1_id is not None:
                personaje1 = Personaje.query.get(personaje1_id)
                if not personaje1:
                    flash(f"El personaje del J1 de la ronda {ronda_num} no existe en la base de datos", "danger")
                    return redirect(url_for('gestion_matchups', ronda_id=ronda_id))

            if personaje2_id is not None:
                personaje2 = Personaje.query.get(personaje2_id)
                if not personaje2:
                    flash(f"El personaje del J2 de la ronda {ronda_num} no existe en la base de datos", "danger")
                    return redirect(url_for('gestion_matchups', ronda_id=ronda_id))

            if ganador_id is not None and ganador_id not in [match.jugador1_id, match.jugador2_id]:
                flash(f"El ganador de la ronda {ronda_num} no es uno de los jugadores del match", "danger")
                return redirect(url_for('gestion_matchups', ronda_id=ronda_id))

            # Anunar ID personajes si no hay un ganador para esa ronda
            if ganador_id is None:
                personaje1_id = None
                personaje2_id = None

            # Asignar valores según el orden
            if orden_coincide:
                setattr(match, f'personaje1r{ronda_num}_id', personaje1_id)
                setattr(match, f'personaje2r{ronda_num}_id', personaje2_id)
                setattr(match, f'ganador_r{ronda_num}', ganador_id)
            else:
                # Invertir valores si el orden está cambiado
                setattr(match, f'personaje1r{ronda_num}_id', personaje2_id)
                setattr(match, f'personaje2r{ronda_num}_id', personaje1_id)
                setattr(match, f'ganador_r{ronda_num}', ganador_id)

            # Contar victorias
            if ganador_id == match.jugador1_id:
                victorias_j1 += 1
            elif ganador_id == match.jugador2_id:
                victorias_j2 += 1

        # Determinar ganador del match
        if victorias_j1 > victorias_j2 and victorias_j1 >= 3:
            match.ganador_match = match.jugador1_id
        elif victorias_j2 > victorias_j1 and victorias_j2 >= 3:
            match.ganador_match = match.jugador2_id
        else:
            flash("Cantidad de partidas insuficientes, aun no se puede determinar el ganador", "warning")
            match.ganador_match = None
            # return redirect(url_for('gestion_matchups', ronda_id=ronda_id))
        app.logger.info(f"Ganador Match: {match.ganador_match}")

        # Guardar videos
        match.videos = videos

        db.session.commit()
        flash('Resultados guardados!', 'success')
        utils.actualizar_personajes_participantes_logic(app, API_TORNEOS_URL)
        return redirect(url_for('gestion_matchups', ronda_id=ronda_id))

    return render_template('matchups.html', ronda=ronda, todos_personajes=todos_personajes)

# =============================================================================
# Torneos
# =============================================================================

# Se planea usar https://github.com/Drarig29/brackets-manager.js
@app.route('/evento/torneos/<int:evento_id>', methods=['GET', 'POST'])
@login_required
def gestion_torneos(evento_id):
    evento = Evento.query.get_or_404(evento_id)

    if request.method == 'POST':
        if not utils.verificar_permiso_tipo(*utils.TIPOS_ADMIN_LIDER):
            return redirect(url_for('gestion_torneos', evento_id=evento_id))

        if not evento.activo:
            flash('Evento bloqueado, no se pueden crear torneos', 'danger')
            return redirect(url_for('gestion_torneos', evento_id=evento_id))

        # Construir datos del torneo desde el formulario
        datos_torneo = {
            'tournamentId': 0,
            'name': request.form.get('name'),
            'type': request.form.get('type'),
            'seeding': json.loads(request.form.get('seeding', '[]')),
            'settings': {
                'balanceByes': 'balanceByes' in request.form,
                'consolationFinal': 'consolationFinal' in request.form,
                'grandFinal': request.form.get('grandFinal') or None,
                'groupCount': request.form.get('groupCount', type=int) or None,
                'manualOrdering': request.form.get('manualOrdering') or None,
                'matchesChildCount': request.form.get('matchesChildCount', type=int) or None,
                'roundRobinMode': request.form.get('roundRobinMode') or None,
                'seedOrdering': json.loads(request.form.get('seedOrdering', '[]')),
                'size': request.form.get('size', type=int) or None,
                'skipFirstRound': 'skipFirstRound' in request.form,   
            }
        }

        # --- Validaciones ---
        # 1. Campos requeridos
        if not datos_torneo['name']:
            flash('El nombre del torneo es obligatorio', 'danger')
            return redirect(url_for('gestion_torneos', evento_id=evento_id))
        if not datos_torneo['type']:
            flash('El tipo de torneo es obligatorio', 'danger')
            return redirect(url_for('gestion_torneos', evento_id=evento_id))
        # Si no se proporcionó size, seeding debe tener al menos un participante
        if not datos_torneo['settings'].get('size') and not datos_torneo['seeding']:
            flash('Debes proporcionar participantes (seeding) o un número de participantes (size)', 'danger')
            return redirect(url_for('gestion_torneos', evento_id=evento_id))

        # 2. Limpiar settings eliminando valores no válidos
        settings = datos_torneo['settings']
        # Valores permitidos
        allowed_grandFinal = {'none', 'simple', 'double'}
        allowed_roundRobinMode = {'simple', 'double'}
        allowed_seedOrdering_methods = {
            'natural', 'reverse', 'half_shift', 'reverse_half_shift', 'pair_flip', 'inner_outer',
            'groups.effort_balanced', 'groups.seed_optimized', 'groups.bracket_optimized'
        }

        cleaned_settings = {}
        for key, value in settings.items():
            if key in ('balanceByes', 'consolationFinal', 'skipFirstRound'):
                # Booleanos: solo incluir si son True
                if value:
                    cleaned_settings[key] = True
            elif key == 'grandFinal':
                if value in allowed_grandFinal:
                    cleaned_settings[key] = value
            elif key == 'groupCount':
                if value and value >= 1:
                    cleaned_settings[key] = value
            elif key == 'manualOrdering':
                if value:
                    try:
                        # Intentar parsear como JSON; debe ser una lista de listas
                        parsed = json.loads(value) if isinstance(value, str) else value
                        if isinstance(parsed, list) and all(isinstance(item, list) for item in parsed):
                            cleaned_settings[key] = parsed
                        else:
                            flash('El formato de manualOrdering no es válido, se ignorará', 'warning')
                    except:
                        flash('El formato de manualOrdering no es válido, se ignorará', 'warning')
            elif key == 'matchesChildCount':
                if value is not None and value >= 0:
                    cleaned_settings[key] = value
            elif key == 'roundRobinMode':
                if value in allowed_roundRobinMode:
                    cleaned_settings[key] = value
            elif key == 'seedOrdering':
                if value and isinstance(value, list):
                    # Filtrar solo métodos válidos
                    valid_seed = [m for m in value if m in allowed_seedOrdering_methods]
                    if valid_seed:
                        cleaned_settings[key] = valid_seed
            elif key == 'size':
                if value and value >= 1:
                    cleaned_settings[key] = value

        datos_torneo['settings'] = cleaned_settings

        app.logger.info(f"Datos a enviar a la API: {datos_torneo}")

        # Enviar a la API externa
        respuesta = utils.api_request('POST', f"{API_TORNEOS_URL}/tournaments", json=datos_torneo)
        if 'error' in respuesta:
            flash(respuesta['error'], 'danger')
        else:
            stage_id = respuesta.get('stageId')
            if stage_id is None or stage_id < 0:
                flash('La respuesta de la API no contiene stageId', 'danger')
            else:
                nuevo_torneo = Torneo(
                    evento_id=evento_id,
                    torneo_id_externo=stage_id,
                    nombre=datos_torneo.get('name', 'Torneo sin nombre')
                )
                db.session.add(nuevo_torneo)
                db.session.commit()
                flash('Torneo creado exitosamente', 'success')

        return redirect(url_for('gestion_torneos', evento_id=evento_id))

    torneos = Torneo.query.filter_by(evento_id=evento_id).all()
    standings_dict = {}

    for torneo in torneos:
        resultado = utils.obtener_standings_torneo(torneo, API_TORNEOS_URL)
        standings_dict[torneo.id] = resultado
    
    return render_template('torneos.html', evento=evento, torneos=torneos, standings=standings_dict)

@app.route('/evento/torneo/editar', methods=['POST'])
@login_required
def editar_torneo():
    if not utils.verificar_permiso_tipo(*utils.TIPOS_ADMIN_LIDER):
        return redirect(url_for('gestion_torneos'))
    return redirect(url_for('gestion_torneos'))

@app.route('/evento/torneo/eliminar/<int:torneo_id>', methods=['POST'])
@login_required
def eliminar_torneo(torneo_id):
    torneo = Torneo.query.get_or_404(torneo_id)
    stage_id = torneo.torneo_id_externo
    
    if not utils.verificar_permiso_tipo(*utils.TIPOS_ADMIN_LIDER):
        return redirect(url_for('gestion_torneos', evento_id=torneo.evento_id))

    if not torneo.evento.activo:
        flash('El evento está bloqueado, no se puede eliminar el torneo', 'danger')
        return redirect(url_for('gestion_torneos', evento_id=torneo.evento_id))

    respuesta = utils.api_request('DELETE', f"{API_TORNEOS_URL}/stages/{stage_id}")
    if 'error' in respuesta:
        flash(respuesta['error'], 'danger')
    else:
        try:
            # eliminar resultados y torneo en BD
            TorneoResultado.query.filter_by(torneo_id=torneo.id).delete()
            db.session.delete(torneo)
            db.session.commit()
            utils.actualizar_personajes_participantes_logic(app, API_TORNEOS_URL)
            flash('Torneo eliminado con éxito', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error al eliminar torneo: {str(e)}', 'danger')

    return redirect(url_for('gestion_torneos', evento_id=torneo.evento_id))

@app.route('/evento/torneo/brackets/<int:torneo_id>', methods=['GET', 'POST'])
@login_required
def gestion_brackets(torneo_id):
    torneo = Torneo.query.get_or_404(torneo_id)
    stage_id = torneo.torneo_id_externo

    if request.method == 'POST':
        if not utils.verificar_permiso_tipo(*utils.TIPOS_TODOS_AUTENTICADOS):
            return redirect(url_for('gestion_brackets', torneo_id=torneo_id))

        if not torneo.evento.activo:
            flash('El evento está bloqueado, no se puede modificar el torneo', 'danger')
            return redirect(url_for('gestion_brackets', torneo_id=torneo.id))

        tipo = request.form.get('tipo')
        match_id = request.form.get('match_id')
        if not match_id:
            flash('ID de match no proporcionado', 'danger')
            return redirect(url_for('gestion_brackets', torneo_id=torneo_id))

        if tipo == 'sin_hijos':
            score1 = request.form.get('opponent1_score', type=int)
            score2 = request.form.get('opponent2_score', type=int)
            char1 = request.form.get('opponent1_character', type=int)
            char2 = request.form.get('opponent2_character', type=int)

            if score1 > score2:
                result1, result2 = 'win', 'loss'
            elif score2 > score1:
                result1, result2 = 'loss', 'win'
            else:
                flash('No pueden haber empates', 'warning')
                return redirect(url_for('gestion_brackets', torneo_id=torneo_id))

            payload = {
                'opponent1': {
                    'score': score1,
                    'result': result1,
                    'personaje': char1
                },
                'opponent2': {
                    'score': score2,
                    'result': result2,
                    'personaje': char2
                }
            }
            
            respuesta = utils.api_request('PATCH', f"{API_TORNEOS_URL}/matches/{match_id}", json=payload)
            if 'error' in respuesta:
                flash(respuesta['error'], 'danger')
            else:
                flash('Match actualizado correctamente', 'success')

        elif tipo == 'con_hijos':
            game_indices = []
            for key in request.form.keys():
                if key.startswith('match_game_id_'):
                    idx = key.replace('match_game_id_', '')
                    game_indices.append(int(idx))
            if not game_indices:
                flash('No se recibieron juegos hijos', 'danger')
                return redirect(url_for('gestion_brackets', torneo_id=torneo_id))

            game_indices.sort()
            total_games = len(game_indices)
            victorias_op1 = 0
            victorias_op2 = 0
            victorias_necesarias = (total_games + 1) // 2

            any_error = False
            for idx in game_indices:
                if victorias_op1 >= victorias_necesarias or victorias_op2 >= victorias_necesarias:
                    break

                game_id = request.form.get(f'match_game_id_{idx}')
                score1 = request.form.get(f'opponent1_score_{idx}', type=int)
                score2 = request.form.get(f'opponent2_score_{idx}', type=int)
                char1 = request.form.get(f'opponent1_character_{idx}', type=int)
                char2 = request.form.get(f'opponent2_character_{idx}', type=int)

                if (score1 or score2):
                    if score1 > score2:
                        result1, result2 = 'win', 'loss'
                        victorias_op1 += 1
                    elif score2 > score1:
                        result1, result2 = 'loss', 'win'
                        victorias_op2 += 1
                    else:
                        flash(f'No pueden haber empates, ajustar resultados de la partida #{idx}', 'warning')
                        return redirect(url_for('gestion_brackets', torneo_id=torneo_id))

                    payload = {
                        'opponent1': {
                            'score': score1,
                            'result': result1,
                            'personaje': char1
                        },
                        'opponent2': {
                            'score': score2,
                            'result': result2,
                            'personaje': char2
                        }
                    }
                    
                    respuesta = utils.api_request('PATCH', f"{API_TORNEOS_URL}/match-games/{game_id}", json=payload)
                    if 'error' in respuesta:
                        flash(respuesta['error'], 'danger')
                        any_error = True
                        break

            if not any_error:
                flash('Juegos actualizados correctamente', 'success')
        else:
            flash('Tipo de actualización desconocido', 'danger')

        return redirect(url_for('gestion_brackets', torneo_id=torneo_id))

    data = utils.api_request('GET', f"{API_TORNEOS_URL}/stages/{stage_id}")
    if 'error' in data:
        flash(data['error'], 'danger')
        return redirect(url_for('gestion_torneos', evento_id=torneo.evento_id))

    current_matches_data = utils.api_request('GET', f"{API_TORNEOS_URL}/stage/{stage_id}/current-matches")
    if 'error' in current_matches_data:
        flash(current_matches_data['error'], 'danger')
        return redirect(url_for('gestion_torneos', evento_id=torneo.evento_id))
    current_matches = current_matches_data.get('currentMatches', [])

    personajes = Personaje.query.order_by(Personaje.nombre).all()
    todos_personajes = [{'id': p.id, 'nombre': p.nombre} for p in personajes]

    standings_data = utils.obtener_standings_torneo(torneo, API_TORNEOS_URL)

    if not 'error' in standings_data:
        utils.actualizar_personajes_participantes_logic(app, API_TORNEOS_URL)

    return render_template('torneo_brackets.html', 
                           torneo=torneo, 
                           stage_data=data,
                           current_matches=current_matches,
                           todos_personajes=todos_personajes,
                           standings_data=standings_data)

# =============================================================================
# Estadísticas
# =============================================================================

# Index Estadisticas
@app.route('/estadisticas')
def mostrar_estadisticas():
    participantes = Participante.query.all()
    personajes = Personaje.query.all()

    # Verificar si hay datos para mostrar
    has_data = any(
        p.matches_como_jugador1 or p.matches_como_jugador2
        for p in participantes
    )

    if not has_data:
        return render_template('estadisticas.html',
                              stats=None,
                              participantes=participantes,
                              personajes=personajes,
                              mensaje="No hay datos estadísticos disponibles")

    stats = utils.calcular_winrates(participantes, personajes, API_TORNEOS_URL)
    return render_template('estadisticas.html',
                          stats=stats,
                          participantes=participantes,
                          personajes=personajes,
                          mensaje=None)

# =============================================================================
# Historial
# =============================================================================

# No hay index Historial
@app.route('/historial')
def historial_redirect():
    return redirect(url_for('mostrar_estadisticas'))

# Historial Participante
@app.route('/historial/<int:id>')
def historial_participante(id):
    participante = Participante.query.get(id)

    if not participante:
        flash('Participante no existe', 'danger')
        return redirect(url_for('mostrar_estadisticas'))

    # Obtener todos los matches del participante (como jugador1 y jugador2)
    # Filtrar solo matches completados (con ganador_match)
    matches_j1 = Match.query.filter(
        Match.jugador1_id == id,
        Match.ganador_match != None
    ).all()

    matches_j2 = Match.query.filter(
        Match.jugador2_id == id,
        Match.ganador_match != None
    ).all()

    # Combinar y ordenar por fecha (más reciente primero)
    todos_matches = matches_j1 + matches_j2
    todos_matches.sort(key=lambda m: m.fecha, reverse=True)

    # Preparar datos para cada match
    datos_matches = []
    for match in todos_matches:
        # Determinar si es jugador1 o jugador2
        es_jugador1 = (match.jugador1_id == id)
        oponente = match.jugador2 if es_jugador1 else match.jugador1

        # Calcular victorias por ronda
        victorias_participante = 0
        victorias_oponente = 0

        # Recolectar personajes únicos usados
        personajes_participante = set()
        personajes_oponente = set()

        # Para cada ronda (1-5)
        for ronda_num in range(1, 6):
            # Obtener ganador de la ronda
            ganador_id = getattr(match, f'ganador_r{ronda_num}')

            # Contar victorias
            if ganador_id == id:
                victorias_participante += 1
            elif ganador_id == oponente.id:
                victorias_oponente += 1

            # Recolectar personajes
            if es_jugador1:
                personaje_id = getattr(match, f'personaje1r{ronda_num}_id')
                if personaje_id:
                    personajes_participante.add(personaje_id)

                personaje_id = getattr(match, f'personaje2r{ronda_num}_id')
                if personaje_id:
                    personajes_oponente.add(personaje_id)
            else:
                personaje_id = getattr(match, f'personaje1r{ronda_num}_id')
                if personaje_id:
                    personajes_oponente.add(personaje_id)

                personaje_id = getattr(match, f'personaje2r{ronda_num}_id')
                if personaje_id:
                    personajes_participante.add(personaje_id)

        # Convertir sets a listas de objetos Personaje
        personajes_participante_objs = Personaje.query.filter(Personaje.id.in_(personajes_participante)).all()
        personajes_oponente_objs = Personaje.query.filter(Personaje.id.in_(personajes_oponente)).all()

        # Determinar resultado
        resultado = "Ganador" if match.ganador_match == id else "Perdedor"

        datos_matches.append({
            'fecha': match.fecha,
            'ronda': match.ronda.nombre,
            'evento': match.ronda.evento.fecha,
            'resultado': resultado,
            'oponente': oponente,
            'personajes_participante': personajes_participante_objs,
            'personajes_oponente': personajes_oponente_objs,
            'victorias_participante': victorias_participante,
            'victorias_oponente': victorias_oponente,
            'videos': match.videos
        })

    # Obtener torneos en los que participó
    resultados_torneo = TorneoResultado.query.filter_by(participante_id=id).all()
    torneos_data = []
    for res in resultados_torneo:
        torneo = res.torneo
        stage_data = utils.api_request('GET', f"{API_TORNEOS_URL}/stages/{torneo.torneo_id_externo}")
        if 'error' in stage_data or stage_data is None:
            continue
        # Buscar el id del participante en la API
        participant_id_api = None
        for part in stage_data.get('participant', []):
            if part and part.get('name') == participante.nickname:
                participant_id_api = part.get('id')
                break
        if participant_id_api is None:
            continue
        # Recolectar personajes usados en el torneo
        personajes_ids = set()
        # Matches sin hijos
        for match in stage_data.get('match', []):
            if match is None:
                continue
            # Solo considerar matches sin hijos
            if match.get('child_count') == 0:
                # Verificar opponent1
                opp1 = match.get('opponent1')
                if opp1 and opp1.get('id') == participant_id_api:
                    pid = opp1.get('personaje')
                    if pid:
                        personajes_ids.add(pid)
                # Verificar opponent2
                opp2 = match.get('opponent2')
                if opp2 and opp2.get('id') == participant_id_api:
                    pid = opp2.get('personaje')
                    if pid:
                        personajes_ids.add(pid)
        # Match games (para matches con hijos)
        for game in stage_data.get('match_game', []):
            if game is None:
                continue
            # Verificar opponent1
            opp1 = game.get('opponent1')
            if opp1 and opp1.get('id') == participant_id_api:
                pid = opp1.get('personaje')
                if pid:
                    personajes_ids.add(pid)
            # Verificar opponent2
            opp2 = game.get('opponent2')
            if opp2 and opp2.get('id') == participant_id_api:
                pid = opp2.get('personaje')
                if pid:
                    personajes_ids.add(pid)
        personajes_objs = Personaje.query.filter(Personaje.id.in_(personajes_ids)).all() if personajes_ids else []
        resultado = "Ganador" if res.ranking == 1 else "Perdedor"
        torneos_data.append({
            'torneo': torneo,
            'ranking': res.ranking,
            'resultado': resultado,
            'personajes': personajes_objs,
            'evento': torneo.evento,
        })
    
    # Agrupar por evento
    eventos_dict = {}
    # Matches de rondas
    for match in datos_matches:
        evento = match['evento']
    # Rehacer: primero construir eventos_dict con los matches originales.
    eventos_dict = {}
    for match in todos_matches:
        evento = match.ronda.evento
        if evento.id not in eventos_dict:
            eventos_dict[evento.id] = {
                'evento': evento,
                'rondas': [],
                'torneos': []
            }
        # Añadir el match ya procesado (con los datos listos para mostrar)
        # Buscamos el match procesado en datos_matches (por id)
        match_data = next((m for m in datos_matches if m['fecha'] == match.fecha and m['oponente'].id == (match.jugador2_id if match.jugador1_id == id else match.jugador1_id)), None)
        if match_data:
            eventos_dict[evento.id]['rondas'].append(match_data)
        else:
            # Si no se encuentra (no debería), añadir un placeholder
            eventos_dict[evento.id]['rondas'].append(match)

    # Torneos
    for tdata in torneos_data:
        evento = tdata['evento']
        if evento.id not in eventos_dict:
            eventos_dict[evento.id] = {
                'evento': evento,
                'rondas': [],
                'torneos': []
            }
        eventos_dict[evento.id]['torneos'].append(tdata)

    eventos_list = sorted(eventos_dict.values(), key=lambda x: x['evento'].fecha, reverse=True)

    return render_template('historial.html',
                          participante=participante,
                          eventos=eventos_list)

if __name__ == '__main__':
    app.run(debug=True)
