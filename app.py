from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
import os
from models import db, Participante, Personaje, Evento, Asistencia, Ronda, Torneo, Match
import utils
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import atexit
from datetime import datetime
import requests

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
API_TORNEOS_URL = "http://localhost:3000"

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
        return redirect(url_for('gestion_eventos', evento_id=id))

    try:
        # Eliminar rondas asociadas y sus matches
        for ronda in evento.rondas:
            # Eliminar matches de la ronda
            Match.query.filter_by(ronda_id=ronda.id).delete()
            # Eliminar la ronda
            db.session.delete(ronda)

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
# Test Matchups
@app.route('/evento/ronda/test_verificaciones/<int:ronda_id>')
def test_verificaciones(ronda_id):
    ronda = Ronda.query.get_or_404(ronda_id)
    return render_template('test_verificaciones.html', ronda=ronda)

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
            'name': request.form.get('name'),
            'formato': request.form.get('formato'),
            # Agrega aquí otros campos que requiera la API
        }

        # Enviar a la API externa
        try:
            response = requests.post(f"{API_TORNEOS_URL}/tournaments", json=datos_torneo)
            response.raise_for_status()
            resp_json = response.json()
            # Extraer stageId
            stage_id = resp_json.get('stageId')
            if not stage_id:
                flash('La respuesta de la API no contiene stageId', 'danger')
                return redirect(url_for('gestion_torneos', evento_id=evento_id))

            # Guardar en la base de datos
            nuevo_torneo = Torneo(
                evento_id=evento_id,
                torneo_id_externo=stage_id,
                nombre=data.get('name', 'Torneo sin nombre')  # ejemplo, asumiendo que viene en data
            )
            db.session.add(nuevo_torneo)
            db.session.commit()
            flash('Torneo creado exitosamente', 'success')
        except requests.exceptions.RequestException as e:
            flash(f'Error al comunicarse con la API: {str(e)}', 'danger')
        except Exception as e:
            flash(f'Error inesperado: {str(e)}', 'danger')

        return redirect(url_for('gestion_torneos', evento_id=evento_id))

    torneos = Torneo.query.filter_by(evento_id=evento_id).all()
    return render_template('torneos.html', evento=evento, torneos=torneos)

@app.route('/evento/torneo/editar', methods=['POST'])
def editar_torneo():
    return redirect(url_for('gestion_torneos'))

@app.route('/evento/torneo/eliminar/<int:torneo_id>', methods=['POST'])
def eliminar_torneo(torneo_id):
    codigo = request.form.get('codigo_secreto', '')

    if codigo != Codigo_Secreto:
        flash('Código secreto incorrecto', 'danger')
        return redirect(url_for('gestion_torneos'))

    return redirect(url_for('gestion_torneos'))

@app.route('/evento/torneo/brackets/<int:torneo_id>', methods=['GET', 'POST'])
def gestion_brackets(torneo_id):
    if request.method == 'POST':
        return redirect(url_for('gestion_brackets', torneo_id=torneo_id))

    return render_template('torneo_brackets.html')

@app.route('/evento/torneo/brackets/matchups', methods=['GET', 'POST'])
def gestion_brackets_matchups():
    if request.method == 'POST':
        return redirect(url_for('gestion_brackets_matchups'))

    return render_template('torneo_matchup.html')

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

    stats = utils.calcular_winrates(participantes, personajes)
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

    return render_template('historial.html',
                          participante=participante,
                          matches=datos_matches)

if __name__ == '__main__':
    app.run(debug=True)
