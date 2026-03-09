from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
import os
from models import db, Participante, Personaje, Evento, Asistencia, Ronda, Torneo, TorneoResultado, Match
import utils
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import atexit
from datetime import datetime
import json

# Crear la aplicación Flask
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(app.instance_path, 'smash.db')
app.config['SECRET_KEY'] = 'supersecreto'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Asegurar que el directorio de instancias exista
os.makedirs(app.instance_path, exist_ok=True)

# Inicializar la base de datos con la app
db.init_app(app)

# Ejecutar la inicialización al importar
utils.init_db(app)

# Configuración del scheduler
scheduler = BackgroundScheduler()
scheduler.start()

Codigo_Secreto = utils.obtener_Codigo_Secreto()

# Variables
# Variable que indica que Ronda usar para el boton en Index
ronda_actual_id = None
# Variable ajustable para el intervalo (en horas)
INTERVALO_ACTUALIZACION_HORAS = 24
# Variable para el URL del API de Torneos
API_TORNEOS_URL = os.environ.get('API_TORNEOS_URL', 'http://localhost:3000')

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
            utils.actualizar_personajes_participantes_logic(app)
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


@app.template_filter('get_attr')
def get_attr_filter(obj, attr):
    """Filtro para acceder a atributos dinámicos en plantillas Jinja"""
    return getattr(obj, attr, None)

# Context processor para hacer ronda_actual_id disponible en todas las templates
@app.context_processor
def inject_ronda_actual():
    return dict(ronda_actual_id=ronda_actual_id)

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

# Index
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
                         eventos=eventos)

# Configurar Ronda Actual en Index
@app.route('/configurar_ronda_actual', methods=['POST'])
def configurar_ronda_actual():
    global ronda_actual_id

    codigo = request.form.get('codigo_secreto', '')
    ronda_id = request.form.get('ronda_id')

    if codigo != Codigo_Secreto:
        flash('Código secreto incorrecto', 'danger')
        return redirect(url_for('index'))

    # Verificar que la ronda existe
    ronda = Ronda.query.get(ronda_id)
    if not ronda:
        flash('Ronda no encontrada', 'danger')
        return redirect(url_for('index'))

    ronda_actual_id = ronda_id
    flash('Ronda actual configurada correctamente!', 'success')
    return redirect(url_for('index'))


# Participantes
# Index Participantes
@app.route('/participantes', methods=['GET', 'POST'])
def gestion_participantes():
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
@app.route('/participante/actualizar', methods=['POST'])
def actualizar_participante():
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
@app.route('/participantes/actualizar_personajes', methods=['POST'])
def actualizar_personajes_participantes():

    # Obtener todos los participantes
    try:
        app.logger.info("Ejecutando actualización de personajes")
        utils.actualizar_personajes_participantes_logic(app)
        app.logger.info('Personajes de participantes actualizados correctamente')
        flash('Personajes de participantes actualizados correctamente', 'success')
    except Exception as e:
        app.logger.info(f'Error al actualizar personajes: {str(e)}')
        flash(f'Error al actualizar personajes', 'danger')

    return redirect(url_for('gestion_participantes'))

# Retirar/Reactivar participante
@app.route('/participante/eliminar/<int:id>', methods=['POST'])
def eliminar_participante(id):
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
@app.route('/participante/borrar/<int:id>', methods=['POST'])
def borrar_participante(id):
    codigo = request.form.get('codigo_secreto', '')

    if codigo != Codigo_Secreto:
        flash('Código secreto incorrecto', 'danger')
        return redirect(url_for('gestion_participantes'))

    participante = Participante.query.get_or_404(id)

    # Verificar si tiene relaciones antes de eliminar
    tiene_personajes = len(participante.personajes) > 0
    tiene_asistencias = Asistencia.query.filter_by(participante_id=id).first() is not None
    tiene_matches = Match.query.filter(
        (Match.jugador1_id == id) | (Match.jugador2_id == id)
    ).first() is not None

    # Si tiene alguna relación, no permitir eliminación
    if tiene_personajes or tiene_asistencias or tiene_matches:
        mensaje_error = "No se puede eliminar el participante porque tiene "
        razones = []

        if tiene_personajes:
            razones.append("personajes asociados")
        if tiene_asistencias:
            razones.append("asistencias registradas")
        if tiene_matches:
            razones.append("partidas jugadas")

        mensaje_error += ", ".join(razones)
        flash(mensaje_error, 'danger')
        return redirect(url_for('gestion_participantes'))

    # Si no tiene relaciones, proceder con la eliminación
    try:
        # Eliminar el participante
        db.session.delete(participante)
        db.session.commit()
        flash('Participante eliminado permanentemente', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar participante: {str(e)}', 'danger')

    return redirect(url_for('gestion_participantes'))

# Personajes
# Index Personajes
@app.route('/personajes', methods=['GET', 'POST'])
def gestion_personajes():
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
@app.route('/personaje/editar/<int:id>', methods=['POST'])
def editar_personaje(id):
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
@app.route('/personaje/eliminar/<int:id>', methods=['POST'])
def eliminar_personaje(id):
    personaje = Personaje.query.get_or_404(id)
    codigo = request.form.get('codigo_secreto', '')

    if codigo != Codigo_Secreto:
        flash('Código secreto incorrecto', 'danger')
        return redirect(url_for('gestion_personajes'))

    # Verificar si el personaje está asociado a algún participante
    if personaje.participantes:
        flash('No se puede eliminar: el personaje está asociado a participantes', 'danger')
        return redirect(url_for('gestion_personajes'))

    # Verificar si el personaje está presente en algún match
    # Revisar todos los campos de personaje en la tabla Match (rondas 1-5 para ambos jugadores)
    campos_personaje = [
        'personaje1r1_id', 'personaje2r1_id',
        'personaje1r2_id', 'personaje2r2_id',
        'personaje1r3_id', 'personaje2r3_id',
        'personaje1r4_id', 'personaje2r4_id',
        'personaje1r5_id', 'personaje2r5_id'
    ]

    for campo in campos_personaje:
        # Verificar si existe algún match donde este campo tenga el ID del personaje
        match_con_personaje = Match.query.filter(getattr(Match, campo) == id).first()
        if match_con_personaje:
            flash('No se puede eliminar: el personaje está registrado en partidas existentes', 'danger')
            return redirect(url_for('gestion_personajes'))

    try:
        db.session.delete(personaje)
        db.session.commit()
        flash('Personaje eliminado con éxito', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar personaje: {str(e)}', 'danger')

    return redirect(url_for('gestion_personajes'))

# Evento
# Index Evento
@app.route('/eventos', methods=['GET', 'POST'])
def gestion_eventos():
    if request.method == 'POST':
        from datetime import datetime
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
def registrar_asistencia(evento_id):
    evento = Evento.query.get_or_404(evento_id)

    if request.method == 'POST':

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
def activar_desactivar_evento(id):
    codigo = request.form.get('codigo_secreto', '')

    if codigo != Codigo_Secreto:
        flash('Código secreto incorrecto', 'danger')
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
def eliminar_evento(id):
    codigo = request.form.get('codigo_secreto', '')

    if codigo != Codigo_Secreto:
        flash('Código secreto incorrecto', 'danger')
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

# Rondas
# Index Rondas
@app.route('/evento/rondas/<int:evento_id>', methods=['GET', 'POST'])
def gestion_rondas(evento_id):
    evento = Evento.query.get_or_404(evento_id)

    if request.method == 'POST':
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
def editar_ronda(id):
    ronda = Ronda.query.get_or_404(id)

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
def eliminar_ronda(id):
    codigo = request.form.get('codigo_secreto', '')

    if codigo != Codigo_Secreto:
        flash('Código secreto incorrecto', 'danger')
        ronda = Ronda.query.get_or_404(id)
        return redirect(url_for('gestion_rondas', evento_id=ronda.evento_id))

    ronda = Ronda.query.get_or_404(id)
    evento_id = ronda.evento_id

    # Comprobar si el evento esta activo
    evento = Evento.query.get(evento_id)
    if not evento.activo:
        flash('Evento bloqueado, No se pueden eliminar las rondas', 'danger')
        return redirect(url_for('gestion_rondas', evento_id=evento_id))

    # Eliminar todos los matches de la ronda
    Match.query.filter_by(ronda_id=id).delete()
    # Eliminar la Ronda
    db.session.delete(ronda)
    db.session.commit()
    flash('Ronda eliminada!', 'success')
    return redirect(url_for('gestion_rondas', evento_id=evento_id))

# Matchups
# Index Matchups
@app.route('/evento/ronda/matchups/<int:ronda_id>', methods=['GET', 'POST'])
def gestion_matchups(ronda_id):
    ronda = Ronda.query.get_or_404(ronda_id)
    todos_personajes = Personaje.query.order_by(Personaje.nombre).all()

    # Verificar si es una prueba
    test_mode = request.form.get('test_mode') == 'true'

    if request.method == 'POST':

        # Comprobar si el evento esta activo
        evento = Evento.query.get(ronda.evento_id)
        if not evento.activo:
            flash('Evento bloqueado, No se pueden modificar los matchups', 'danger')
            return redirect(url_for('gestion_matchups', ronda_id=ronda.id))

        if test_mode:
            app.logger.info("=== MODO PRUEBA ACTIVADO ===")
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
        return redirect(url_for('gestion_matchups', ronda_id=ronda_id))

    return render_template('matchups.html', ronda=ronda, todos_personajes=todos_personajes)

# Torneos (Aun no implementado)
# Se planea usar https://github.com/Drarig29/brackets-manager.js
@app.route('/evento/torneos/<int:evento_id>', methods=['GET', 'POST'])
def gestion_torneos(evento_id):
    evento = Evento.query.get_or_404(evento_id)

    if request.method == 'POST':
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
def editar_torneo():
    return redirect(url_for('gestion_torneos'))

@app.route('/evento/torneo/eliminar/<int:torneo_id>', methods=['POST'])
def eliminar_torneo(torneo_id):
    codigo = request.form.get('codigo_secreto', '')
    torneo = Torneo.query.get_or_404(torneo_id)
    stage_id = torneo.torneo_id_externo
    
    if codigo != Codigo_Secreto:
        flash('Código secreto incorrecto', 'danger')
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
            flash('Torneo eliminado con éxito', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error al eliminar torneo: {str(e)}', 'danger')

    return redirect(url_for('gestion_torneos', evento_id=torneo.evento_id))

@app.route('/evento/torneo/brackets/<int:torneo_id>', methods=['GET', 'POST'])
def gestion_brackets(torneo_id):
    torneo = Torneo.query.get_or_404(torneo_id)
    stage_id = torneo.torneo_id_externo

    if request.method == 'POST':
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

    return render_template('torneo_brackets.html', 
                           torneo=torneo, 
                           stage_data=data,
                           current_matches=current_matches,
                           todos_personajes=todos_personajes,
                           standings_data=standings_data)

# Estadisticas
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

# Historial
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
        if 'error' in stage_data:
            continue
        # Buscar el id del participante en la API
        participant_id_api = None
        for part in stage_data.get('participant', []):
            if part['name'] == participante.nickname:
                participant_id_api = part['id']
                break
        if participant_id_api is None:
            continue
        # Recolectar personajes usados en el torneo
        personajes_ids = set()
        # Matches sin hijos
        for match in stage_data.get('match', []):
            if match.get('child_count') == 0:
                if match.get('opponent1', {}).get('id') == participant_id_api:
                    pid = match.get('opponent1', {}).get('personaje')
                    if pid:
                        personajes_ids.add(pid)
                if match.get('opponent2', {}).get('id') == participant_id_api:
                    pid = match.get('opponent2', {}).get('personaje')
                    if pid:
                        personajes_ids.add(pid)
        # Match games (para matches con hijos)
        for game in stage_data.get('match_game', []):
            if game.get('opponent1', {}).get('id') == participant_id_api:
                pid = game.get('opponent1', {}).get('personaje')
                if pid:
                    personajes_ids.add(pid)
            if game.get('opponent2', {}).get('id') == participant_id_api:
                pid = game.get('opponent2', {}).get('personaje')
                if pid:
                    personajes_ids.add(pid)
        personajes_objs = Personaje.query.filter(Personaje.id.in_(personajes_ids)).all()
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
