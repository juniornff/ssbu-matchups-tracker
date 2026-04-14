from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class TipoUsuario(db.Model):
    """
    Representa el tipo/rol de un usuario en el sistema.
    Los permisos por tipo se definen manualmente en el código por acción.
    Ejemplos de tipos iniciales: Admin, Líder de liga, Participante.
    """
    __tablename__ = 'tipo_usuario'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), unique=True, nullable=False)

    # Relación inversa: usuarios de este tipo
    usuarios = db.relationship('Usuario', backref='tipo', lazy=True)

    def __repr__(self):
        return f'<TipoUsuario {self.nombre}>'


class Usuario(UserMixin, db.Model):
    """
    Representa una cuenta de usuario del sistema.
    Un usuario puede o no estar vinculado a un Participante.
    La verificación de email y la recuperación de contraseña
    se gestionan mediante tokens con expiración.
    
    Campos de autenticación:
    - email: identificador único para login
    - password_hash: contraseña hasheada con bcrypt
    - activo: permite desactivar cuentas sin eliminarlas
    - email_verificado: la cuenta está bloqueada hasta que se verifique

    Campos para verificación de email (para uso futuro con SMTP):
    - token_verificacion: token único enviado al email al registrarse
    - token_verificacion_expiracion: fecha límite para usar el token

    Campos para recuperación de contraseña (para uso futuro con SMTP):
    - token_recuperacion: token único enviado al email para resetear contraseña
    - token_recuperacion_expiracion: fecha límite para usar el token
    """
    __tablename__ = 'usuario'

    id = db.Column(db.Integer, primary_key=True)

    # --- Credenciales ---
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

    # --- Estado de la cuenta ---
    activo = db.Column(db.Boolean, default=True, nullable=False)

    # --- Verificación de email ---
    # Indica si el usuario ha verificado su email
    # La cuenta está bloqueada para login hasta que sea True
    email_verificado = db.Column(db.Boolean, default=False, nullable=False)
    # Token enviado al email para verificar la cuenta
    token_verificacion = db.Column(db.String(256), unique=True, nullable=True)
    # Fecha límite para usar el token de verificación
    token_verificacion_expiracion = db.Column(db.DateTime, nullable=True)

    # --- Recuperación de contraseña ---
    # Token enviado al email para restablecer la contraseña
    token_recuperacion = db.Column(db.String(256), unique=True, nullable=True)
    # Fecha límite para usar el token de recuperación
    token_recuperacion_expiracion = db.Column(db.DateTime, nullable=True)

    # --- Relaciones ---
    # Tipo de usuario (Admin, Líder de liga, Participante, etc.)
    tipo_id = db.Column(db.Integer, db.ForeignKey('tipo_usuario.id'), nullable=False)

    # Participante vinculado (opcional, único: un usuario <-> un participante)
    participante_id = db.Column(
        db.Integer,
        db.ForeignKey('participante.id'),
        nullable=True,
        unique=True  # Un participante no puede tener más de un usuario
    )
    participante = db.relationship(
        'Participante',
        backref=db.backref('usuario', uselist=False)  # Acceso inverso: participante.usuario
    )

    # --- Auditoría ---
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    fecha_ultimo_login = db.Column(db.DateTime, nullable=True)

    @property
    def is_active(self):
        """
        Flask-Login llama a esta propiedad para saber si el usuario puede
        autenticarse. Se requiere que la cuenta esté activa Y con email verificado.
        """
        return self.activo and self.email_verificado

    def __repr__(self):
        return f'<Usuario {self.email}>'


class Participante(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nickname = db.Column(db.String(50), unique=True, nullable=False)
    activo = db.Column(db.Boolean, default=True)
    personajes = db.relationship('Personaje', secondary='participante_personaje', backref='participantes')
    asistencias = db.relationship('Asistencia', backref='participante')
    matches_como_jugador1 = db.relationship('Match', foreign_keys='Match.jugador1_id', backref='jugador1')
    matches_como_jugador2 = db.relationship('Match', foreign_keys='Match.jugador2_id', backref='jugador2')

class Personaje(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), unique=True, nullable=False)

# Tabla de asociación para relación muchos-a-muchos
participante_personaje = db.Table('participante_personaje',
    db.Column('participante_id', db.Integer, db.ForeignKey('participante.id')),
    db.Column('personaje_id', db.Integer, db.ForeignKey('personaje.id'))
)

class Evento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date, nullable=False)
    activo = db.Column(db.Boolean, default=True)
    asistencias = db.relationship('Asistencia', backref='evento')
    rondas = db.relationship('Ronda', backref='evento')

class Asistencia(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    evento_id = db.Column(db.Integer, db.ForeignKey('evento.id'))
    participante_id = db.Column(db.Integer, db.ForeignKey('participante.id'))

class Ronda(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100))
    evento_id = db.Column(db.Integer, db.ForeignKey('evento.id'))
    matches = db.relationship('Match', backref='ronda')

class Torneo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    evento_id = db.Column(db.Integer, db.ForeignKey('evento.id'), nullable=False)
    torneo_id_externo = db.Column(db.Integer, nullable=False)
    nombre = db.Column(db.String(200), nullable=False)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

    # Relación con Evento
    evento = db.relationship('Evento', backref=db.backref('torneos', lazy=True))

class TorneoResultado(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    torneo_id = db.Column(db.Integer, db.ForeignKey('torneo.id'), nullable=False)
    participante_id = db.Column(db.Integer, db.ForeignKey('participante.id'), nullable=False)
    ranking = db.Column(db.Integer, nullable=False)

    # Relaciones
    torneo = db.relationship('Torneo', backref=db.backref('resultados', lazy=True))
    participante = db.relationship('Participante', backref=db.backref('resultados_torneo', lazy=True))

class Match(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ronda_id = db.Column(db.Integer, db.ForeignKey('ronda.id'))
    jugador1_id = db.Column(db.Integer, db.ForeignKey('participante.id'))
    jugador2_id = db.Column(db.Integer, db.ForeignKey('participante.id'))
    # Ronda 1
    personaje1r1_id = db.Column(db.Integer, db.ForeignKey('personaje.id'))
    personaje2r1_id = db.Column(db.Integer, db.ForeignKey('personaje.id'))
    ganador_r1 = db.Column(db.Integer, db.ForeignKey('participante.id'))
    # Ronda 2
    personaje1r2_id = db.Column(db.Integer, db.ForeignKey('personaje.id'))
    personaje2r2_id = db.Column(db.Integer, db.ForeignKey('personaje.id'))
    ganador_r2 = db.Column(db.Integer, db.ForeignKey('participante.id'))
    # Ronda 3
    personaje1r3_id = db.Column(db.Integer, db.ForeignKey('personaje.id'))
    personaje2r3_id = db.Column(db.Integer, db.ForeignKey('personaje.id'))
    ganador_r3 = db.Column(db.Integer, db.ForeignKey('participante.id'))
    # Ronda 4
    personaje1r4_id = db.Column(db.Integer, db.ForeignKey('personaje.id'))
    personaje2r4_id = db.Column(db.Integer, db.ForeignKey('personaje.id'))
    ganador_r4 = db.Column(db.Integer, db.ForeignKey('participante.id'))
    # Ronda 5
    personaje1r5_id = db.Column(db.Integer, db.ForeignKey('personaje.id'))
    personaje2r5_id = db.Column(db.Integer, db.ForeignKey('personaje.id'))
    ganador_r5 = db.Column(db.Integer, db.ForeignKey('participante.id'))
    # Resultados
    ganador_match = db.Column(db.Integer, db.ForeignKey('participante.id'))
    videos = db.Column(db.String(500))
    fecha = db.Column(db.DateTime, default=datetime.utcnow)

    # Relaciones para acceso directo
    personaje1r1_rel = db.relationship('Personaje', foreign_keys=[personaje1r1_id])
    personaje2r1_rel = db.relationship('Personaje', foreign_keys=[personaje2r1_id])
    ganador_r1_rel = db.relationship('Participante', foreign_keys=[ganador_r1])
    personaje1r2_rel = db.relationship('Personaje', foreign_keys=[personaje1r2_id])
    personaje2r2_rel = db.relationship('Personaje', foreign_keys=[personaje2r2_id])
    ganador_r2_rel = db.relationship('Participante', foreign_keys=[ganador_r2])
    personaje1r3_rel = db.relationship('Personaje', foreign_keys=[personaje1r3_id])
    personaje2r3_rel = db.relationship('Personaje', foreign_keys=[personaje2r3_id])
    ganador_r3_rel = db.relationship('Participante', foreign_keys=[ganador_r3])
    personaje1r4_rel = db.relationship('Personaje', foreign_keys=[personaje1r4_id])
    personaje2r4_rel = db.relationship('Personaje', foreign_keys=[personaje2r4_id])
    ganador_r4_rel = db.relationship('Participante', foreign_keys=[ganador_r4])
    personaje1r5_rel = db.relationship('Personaje', foreign_keys=[personaje1r5_id])
    personaje2r5_rel = db.relationship('Personaje', foreign_keys=[personaje2r5_id])
    ganador_r5_rel = db.relationship('Participante', foreign_keys=[ganador_r5])
    ganador_match_rel = db.relationship('Participante', foreign_keys=[ganador_match])
