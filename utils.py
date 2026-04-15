from collections import defaultdict, deque
from models import db, Participante, Personaje, Evento, Asistencia, Ronda, Torneo, TorneoResultado, Match, TipoUsuario, Usuario
import random, string
import requests
import json
import os
from flask import current_app, flash
from flask_bcrypt import Bcrypt
from flask_login import current_user
from datetime import datetime

# Instancia de Bcrypt (se inicializa con la app en app.py)
bcrypt = Bcrypt()

# =============================================================================
# Constantes de permisos por tipo de usuario
# =============================================================================

# Solo administradores del sistema
TIPOS_ADMIN = ('Admin',)

# Administradores y líderes de liga
TIPOS_ADMIN_LIDER = ('Admin', 'Líder de liga')

# Todos los usuarios autenticados con un rol activo en la liga
TIPOS_TODOS_AUTENTICADOS = ('Admin', 'Líder de liga', 'Participante')


def verificar_permiso_tipo(*tipos_permitidos):
    """
    Verifica que el usuario actual tenga uno de los tipos de usuario permitidos.

    Debe llamarse dentro de una vista de Flask donde current_user esté disponible.
    Si el usuario no está autenticado o no tiene el tipo requerido, registra
    un flash message de error.

    Args:
        *tipos_permitidos: nombres de los tipos de usuario que pueden
                           realizar la acción (ej: 'Admin', 'Líder de liga').

    Returns:
        bool: True si el usuario tiene permiso, False en caso contrario.

    Ejemplo de uso:
        if not utils.verificar_permiso_tipo(*utils.TIPOS_ADMIN_LIDER):
            return redirect(url_for('index'))
    """
    if not current_user.is_authenticated:
        flash('Debes iniciar sesión para realizar esta acción.', 'warning')
        return False
    if current_user.tipo.nombre not in tipos_permitidos:
        flash('No tienes permisos para realizar esta acción.', 'danger')
        return False
    return True


# =============================================================================
# Listas de datos iniciales
# =============================================================================

# Lista de personajes para inicializar la base de datos
PERSONAJES = [
    "Mario", "Donkey Kong", "Link", "Samus", "Yoshi",
    "Kirby", "Fox", "Pikachu", "Luigi", "Ness",
    "Captain Falcon", "Jigglypuff", "Peach", "Bowser",
    "Sheik", "Zelda", "Dr. Mario", "Pichu", "Falco",
    "Marth", "Lucina", "Young Link", "Ganondorf", "Mewtwo",
    "Roy", "Chrom", "Mr. Game & Watch", "Meta Knight", "Pit",
    "Dark Pit", "Zero Suit Samus", "Wario", "Snake", "Ike",
    "Pokémon Trainer", "Diddy Kong", "Lucas", "Sonic",
    "King Dedede", "Olimar", "Lucario", "R.O.B.", "Toon Link",
    "Wolf", "Villager", "Mega Man", "Wii Fit Trainer", "Rosalina & Luma",
    "Little Mac", "Greninja", "Mii Brawler", "Mii Swordfighter", "Mii Gunner",
    "Palutena", "Pac-Man", "Robin", "Shulk", "Bowser Jr.",
    "Duck Hunt", "Ryu", "Ken", "Cloud", "Corrin",
    "Bayonetta", "Inkling", "Ridley", "Simon", "Richter",
    "King K. Rool", "Isabelle", "Incineroar", "Piranha Plant", "Joker",
    "Hero", "Banjo & Kazooie", "Terry", "Byleth", "Min Min",
    "Steve", "Sephiroth", "Pyra/Mythra", "Kazuya", "Sora", "Ice Climbers", "Dark Samus"
]

def seed_personajes():
    """Agregar personajes a la base de datos si no existen"""
    count = 0
    for nombre in PERSONAJES:
        if not Personaje.query.filter_by(nombre=nombre).first():
            p = Personaje(nombre=nombre)
            db.session.add(p)
            count += 1

    db.session.commit()
    return count

# Tipos de usuario iniciales del sistema
TIPOS_USUARIO = [
    "Admin",
    "Líder de liga",
    "Participante",
    "Espectador"
]

def seed_tipos_usuario():
    """
    Inserta los tipos de usuario iniciales en la base de datos si no existen.
    Los tipos iniciales son: Admin, Líder de liga, Participante.
    Retorna el número de tipos creados.
    """
    count = 0
    for nombre in TIPOS_USUARIO:
        if not TipoUsuario.query.filter_by(nombre=nombre).first():
            tipo = TipoUsuario(nombre=nombre)
            db.session.add(tipo)
            count += 1

    db.session.commit()
    return count


def seed_admin(app):
    """
    Crea el primer usuario Admin si no existe ningún usuario con tipo Admin.

    Lee las credenciales desde variables de entorno:
    - ADMIN_EMAIL: email del usuario Admin
    - ADMIN_PASSWORD: contraseña del usuario Admin

    Si no se proporcionan, genera valores aleatorios y los imprime en consola
    para que el administrador pueda usarlos en el primer acceso.

    Args:
        app: instancia de la aplicación Flask (para acceso al logger)
    """

    # Obtener el tipo Admin de la BD
    tipo_admin = TipoUsuario.query.filter_by(nombre='Admin').first()
    if not tipo_admin:
        app.logger.error('No se encontró el tipo de usuario Admin en la BD. '
                         'Asegúrate de ejecutar seed_tipos_usuario() primero.')
        return

    # Verificar si ya existe algún usuario Admin
    admin_existente = Usuario.query.filter_by(tipo_id=tipo_admin.id).first()
    if admin_existente:
        app.logger.info('Ya existe un usuario Admin. No se creará uno nuevo.')
        return

    # --- Leer credenciales desde variables de entorno ---
    admin_email = os.environ.get('ADMIN_EMAIL')
    admin_password = os.environ.get('ADMIN_PASSWORD')

    # Bandera para saber si se generaron valores aleatorios
    credenciales_generadas = False

    # Generar email aleatorio si no se proporcionó
    if not admin_email:
        sufijo = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        admin_email = f'admin_{sufijo}@smash.local'
        credenciales_generadas = True

    # Generar contraseña aleatoria si no se proporcionó
    if not admin_password:
        # Contraseña de 16 caracteres con letras, números y símbolos seguros
        chars = string.ascii_letters + string.digits + '!@#$%^&*'
        admin_password = ''.join(random.choices(chars, k=16))
        credenciales_generadas = True

    # --- Crear el usuario Admin ---
    password_hash = bcrypt.generate_password_hash(admin_password).decode('utf-8')

    admin = Usuario(
        email=admin_email,
        password_hash=password_hash,
        tipo_id=tipo_admin.id,
        activo=True,
        # El Admin inicial se crea con email verificado para permitir
        # el primer acceso sin necesidad de SMTP (aún no implementado)
        email_verificado=True,
        participante_id=None
    )

    db.session.add(admin)
    db.session.commit()

    # --- Informar al administrador ---
    if credenciales_generadas:
        app.logger.warning('=' * 60)
        app.logger.warning('CREDENCIALES DEL ADMIN GENERADAS AUTOMÁTICAMENTE')
        app.logger.warning('Guárdalas en un lugar seguro y cámbialas después.')
        app.logger.warning(f'  Email:      {admin_email}')
        app.logger.warning(f'  Contraseña: {admin_password}')
        app.logger.warning('=' * 60)
    else:
        app.logger.info(f'Usuario Admin creado exitosamente con email: {admin_email}')

def generar_Codigo_Secreto():
    """
    Genera una contraseña aleatoria de entre 6 y 12 caracteres.
    Retorna el string generado.
    """
    length = random.randint(6, 12)
    chars = string.ascii_letters + string.digits + string.punctuation
    return ''.join(random.choices(chars, k=length))

# =============================================================================
# Lógica de negocio
# =============================================================================

# Función común para actualizar personajes
def actualizar_personajes_participantes_logic(app, api_url):

    # Obtener todos los participantes
    participantes = Participante.query.all()

    app.logger.info("=====Personajes/Jugador=====")
    for participante in participantes:
        # Conjunto para almacenar los IDs de personajes usados por este participante
        personajes_usados = set()

        # Revisar todos los matches del participante (como jugador1 y jugador2)
        for match in participante.matches_como_jugador1 + participante.matches_como_jugador2:
            # Para cada ronda (1-5)
            for ronda_num in range(1, 6):
                # Obtener el personaje usado en esta ronda
                personaje_id = None
                if match.jugador1_id == participante.id:
                    personaje_id = getattr(match, f'personaje1r{ronda_num}_id')
                else:
                    personaje_id = getattr(match, f'personaje2r{ronda_num}_id')

                if personaje_id:
                    personajes_usados.add(personaje_id)
        
        # Obtener torneos en los que participó
        resultados = TorneoResultado.query.filter_by(participante_id=participante.id).all()
        for res in resultados:
            torneo = res.torneo
            stage_id = torneo.torneo_id_externo
            # Obtener datos del torneo desde la API
            stage_data = api_request('GET', f"{api_url}/stages/{stage_id}")
            if 'error' in stage_data or not stage_data:
                continue
            # Buscar el id del participante en la API
            participant_id_api = None
            for part in stage_data.get('participant', []):
                if part and part.get('name') == participante.nickname:
                    participant_id_api = part.get('id')
                    break
            if participant_id_api is None:
                continue
            # Matches sin hijos
            for match in stage_data.get('match', []):
                if match is None or match.get('child_count', 0) != 0:
                    continue
                # opponent1
                op1 = match.get('opponent1')
                if op1 and op1.get('id') == participant_id_api:
                    pid = op1.get('personaje')
                    if pid:
                        personajes_usados.add(pid)
                # opponent2
                op2 = match.get('opponent2')
                if op2 and op2.get('id') == participant_id_api:
                    pid = op2.get('personaje')
                    if pid:
                        personajes_usados.add(pid)
            # Match games
            for game in stage_data.get('match_game', []):
                if game is None:
                    continue
                op1 = game.get('opponent1')
                if op1 and op1.get('id') == participant_id_api:
                    pid = op1.get('personaje')
                    if pid:
                        personajes_usados.add(pid)
                op2 = game.get('opponent2')
                if op2 and op2.get('id') == participant_id_api:
                    pid = op2.get('personaje')
                    if pid:
                        personajes_usados.add(pid)

        # Ahora, actualizar la lista de personajes del participante
        # Primero, eliminamos todos los personajes actuales
        participante.personajes.clear()

        # Luego, añadimos los personajes que se encontraron en los matches
        app.logger.info(f'{participante.nickname}:')
        for personaje_id in personajes_usados:
            personaje = Personaje.query.get(personaje_id)
            if personaje:
                participante.personajes.append(personaje)
                app.logger.info(f'    {personaje.nombre}')
        app.logger.info("============================")

    db.session.commit()

def crear_participante_para_usuario(usuario, nickname):
    """
    Crea un nuevo participante con el nickname dado y lo asocia al usuario.
    Cambia el tipo del usuario a 'Participante' si era 'Espectador'.
    Retorna (bool, mensaje).
    """
    if usuario.participante:
        return False, 'El usuario ya tiene un participante asociado.'
    if not nickname or not nickname.strip():
        return False, 'El nickname no puede estar vacío.'
    nickname = nickname.strip()
    # Verificar unicidad
    if Participante.query.filter_by(nickname=nickname).first():
        return False, 'Este nickname ya está en uso por otro participante.'
    # Crear participante
    participante = Participante(nickname=nickname)
    db.session.add(participante)
    db.session.flush()  # para obtener el id
    usuario.participante_id = participante.id
    # Si el usuario es 'Espectador', cambiar a 'Participante'
    if usuario.tipo and usuario.tipo.nombre == 'Espectador':
        tipo_participante = TipoUsuario.query.filter_by(nombre='Participante').first()
        if tipo_participante:
            usuario.tipo_id = tipo_participante.id
    db.session.commit()
    return True, 'Nickname creado y asociado correctamente.'

def actualizar_nickname_participante(usuario, nuevo_nickname):
    """
    Actualiza el nickname del participante asociado al usuario.
    Verifica que el nickname no esté ya en uso por otro participante.
    Retorna (bool, mensaje).
    """
    if not usuario.participante:
        return False, 'No tienes un perfil de participante asociado a tu cuenta.'
    # Verificar unicidad (excluyendo al propio participante)
    otro = Participante.query.filter(
        Participante.nickname == nuevo_nickname,
        Participante.id != usuario.participante_id
    ).first()
    if otro:
        return False, 'Este nickname ya está en uso por otro participante.'
    usuario.participante.nickname = nuevo_nickname
    db.session.commit()
    return True, 'Nickname actualizado correctamente.'

def api_request(method, url, **kwargs):
    """
    Realiza una petición HTTP a la API externa y maneja errores comunes.
    Retorna el JSON de la respuesta si es exitosa, o un dict con 'error' en caso contrario.
    """
    try:
        response = requests.request(method, url, timeout=5, **kwargs)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        try:
            error_data = e.response.json()
            return {'error': error_data.get('error', f'HTTP {e.response.status_code}')}
        except:
            return {'error': f'HTTP {e.response.status_code}'}
    except requests.exceptions.ConnectionError:
        return {'error': 'Error de conexión con la API'}
    except requests.exceptions.Timeout:
        return {'error': 'Tiempo de espera agotado'}
    except requests.exceptions.RequestException as e:
        return {'error': f'Error: {str(e)}'}

def check_api_connection(api_url):
    """
    Verifica la conexión con la API externa usando el endpoint /health.
    Retorna True si la conexión es exitosa, False en caso contrario.
    """
    resultado = api_request('GET', f"{api_url}/health")
    if 'error' in resultado:
        return False
    return resultado.get('status') == 'OK'

def obtener_standings_torneo(torneo, api_url):
    """
    Obtiene los standings de un torneo desde la API.
    Retorna un diccionario con los datos si éxito, o un dict con 'error'.
    Además, guarda los resultados en la base de datos si no existen.
    """
    stage_id = torneo.torneo_id_externo
    resultado = api_request('GET', f"{api_url}/tournaments/{stage_id}/standings")
    if 'error' in resultado:
        return resultado

    # resultado es el JSON de standings
    standings_data = resultado
    # Guardar en BD si no existen resultados
    resultados_existentes = TorneoResultado.query.filter_by(torneo_id=torneo.id).count()
    if resultados_existentes == 0 and 'standings' in standings_data:
        for item in standings_data['standings']:
            participante = Participante.query.filter_by(nickname=item['name']).first()
            if participante:
                nuevo_resultado = TorneoResultado(
                    torneo_id=torneo.id,
                    participante_id=participante.id,
                    ranking=item['rank']
                )
                db.session.add(nuevo_resultado)
        db.session.commit()
    return standings_data

def generar_round_robin(participantes_ids):
    """Genera todos los enfrentamientos posibles entre participantes"""
    matches = []
    n = len(participantes_ids)
    for i in range(n):
        for j in range(i+1, n):
            matches.append({
                'jugador1_id': participantes_ids[i],
                'jugador2_id': participantes_ids[j]
            })
    return matches

def calcular_winrates(participantes, personajes, api_url):
    stats = {
        'partidos': {
            'general': {},
            'por_personaje': defaultdict(lambda: defaultdict(dict)),
            'por_personaje_parcial': defaultdict(lambda: defaultdict(dict)),
            'contra_oponente': defaultdict(lambda: defaultdict(dict))
        },
        'rondas': {
            'general': {},
            'por_personaje': defaultdict(lambda: defaultdict(dict)),
            'contra_oponente': defaultdict(lambda: defaultdict(dict))
        },
        'torneos': {
            'general': {},
            'por_personaje': defaultdict(lambda: defaultdict(dict)),
            'por_personaje_parcial': defaultdict(lambda: defaultdict(dict)),
            'contra_oponente': defaultdict(lambda: defaultdict(dict))
        }
    }

    # Asegurar que todos los torneos tengan resultados en BD
    todos_los_torneos = Torneo.query.all()
    for torneo in todos_los_torneos:
        # Si ya tiene resultados, no hace falta consultar
        if TorneoResultado.query.filter_by(torneo_id=torneo.id).count() > 0:
            continue
        # Intentar obtener standings (esto guarda en BD si la API responde)
        utils.obtener_standings_torneo(torneo, api_url)

    # Obtener todos los torneos que tienen resultados (para limitar peticiones)
    torneos_con_resultados = db.session.query(Torneo).join(TorneoResultado).distinct().all()
    torneos_data_cache = {}  # clave: torneo.id, valor: datos de API o None si error

    for torneo in torneos_con_resultados:
        stage_id = torneo.torneo_id_externo
        resultado = api_request('GET', f"{api_url}/stages/{stage_id}")
        if 'error' in resultado:
            torneos_data_cache[torneo.id] = None
        else:
            torneos_data_cache[torneo.id] = resultado

    for p in participantes:
        # Estadísticas de partidos
        partidos_ganados = 0
        partidos_jugados = 0

        # Estadísticas de rondas
        rondas_ganadas = 0
        rondas_jugadas = 0

        # Por personaje (para partidos y rondas)
        winrates_personaje_partidos = {pers.id: {'ganados': 0, 'jugados': 0} for pers in p.personajes}
        winrates_personaje_rondas = {pers.id: {'ganadas': 0, 'jugadas': 0} for pers in p.personajes}

        # Nueva estadística: partidos parciales por personaje
        winrates_personaje_parcial = {pers.id: {'ganados': 0, 'jugados': 0} for pers in p.personajes}

        # Contra oponente (para partidos y rondas)
        winrates_vs_partidos = {op.id: {'ganados': 0, 'jugados': 0} for op in participantes if op.id != p.id}
        winrates_vs_rondas = {op.id: {'ganadas': 0, 'jugadas': 0} for op in participantes if op.id != p.id}

        # Revisar todos los matches del participante
        for match in p.matches_como_jugador1 + p.matches_como_jugador2:
            # Solo matches completados
            if match.ganador_match is None:
                continue

            es_jugador1 = (match.jugador1_id == p.id)
            oponente_id = match.jugador2_id if es_jugador1 else match.jugador1_id

            # Estadísticas de partidos
            partidos_jugados += 1
            if match.ganador_match == p.id:
                partidos_ganados += 1

            # Contar partido por personaje (solo si usó el mismo en todas las rondas)
            personaje_unico = None
            mismo_personaje = True
            rondas_jugadas_en_match = 0

            for ronda_num in range(1, 6):
                personaje_id = getattr(match, f'personaje1r{ronda_num}_id') if es_jugador1 else getattr(match, f'personaje2r{ronda_num}_id')

                # Si la ronda se jugó (personaje_id no es None)
                if personaje_id is not None:
                    rondas_jugadas_en_match += 1

                    if personaje_unico is None:
                        personaje_unico = personaje_id
                    elif personaje_id != personaje_unico:
                        mismo_personaje = False

            # Si usó el mismo personaje en todas las rondas jugadas
            if mismo_personaje and personaje_unico is not None and rondas_jugadas_en_match > 0:
                if personaje_unico in winrates_personaje_partidos:
                    winrates_personaje_partidos[personaje_unico]['jugados'] += 1
                    if match.ganador_match == p.id:
                        winrates_personaje_partidos[personaje_unico]['ganados'] += 1

            # NUEVA ESTADÍSTICA: Contar partido para cada personaje usado al menos una vez
            personajes_usados = set()
            for ronda_num in range(1, 6):
                personaje_id = getattr(match, f'personaje1r{ronda_num}_id') if es_jugador1 else getattr(match, f'personaje2r{ronda_num}_id')

                # Si la ronda se jugó (personaje_id no es None)
                if personaje_id is not None:
                    personajes_usados.add(personaje_id)

            # Registrar el partido para cada personaje usado
            for personaje_id in personajes_usados:
                if personaje_id in winrates_personaje_parcial:
                    winrates_personaje_parcial[personaje_id]['jugados'] += 1
                    if match.ganador_match == p.id:
                        winrates_personaje_parcial[personaje_id]['ganados'] += 1

            # Contar partido contra oponente
            if oponente_id in winrates_vs_partidos:
                winrates_vs_partidos[oponente_id]['jugados'] += 1
                if match.ganador_match == p.id:
                    winrates_vs_partidos[oponente_id]['ganados'] += 1

            # Estadísticas de rondas
            for ronda_num in range(1, 6):
                ganador_id = getattr(match, f'ganador_r{ronda_num}')
                if ganador_id is None:
                    continue

                rondas_jugadas += 1

                # Personaje usado en esta ronda
                personaje_id = getattr(match, f'personaje1r{ronda_num}_id') if es_jugador1 else getattr(match, f'personaje2r{ronda_num}_id')

                # Contar ronda
                if ganador_id == p.id:
                    rondas_ganadas += 1

                    # Por personaje
                    if personaje_id and personaje_id in winrates_personaje_rondas:
                        winrates_personaje_rondas[personaje_id]['ganadas'] += 1

                # Contra oponente
                if oponente_id in winrates_vs_rondas:
                    winrates_vs_rondas[oponente_id]['jugadas'] += 1
                    if ganador_id == p.id:
                        winrates_vs_rondas[oponente_id]['ganadas'] += 1

                # Por personaje (rondas jugadas)
                if personaje_id and personaje_id in winrates_personaje_rondas:
                    winrates_personaje_rondas[personaje_id]['jugadas'] += 1

        # Guardar estadísticas generales de partidos
        stats['partidos']['general'][p.id] = {
            'ganados': partidos_ganados,
            'jugados': partidos_jugados,
            'winrate': (partidos_ganados / partidos_jugados * 100) if partidos_jugados > 0 else 0
        }

        # Guardar estadísticas generales de rondas
        stats['rondas']['general'][p.id] = {
            'ganadas': rondas_ganadas,
            'jugadas': rondas_jugadas,
            'winrate': (rondas_ganadas / rondas_jugadas * 100) if rondas_jugadas > 0 else 0
        }

        # Guardar por personaje (partidos completos)
        for pers_id, data in winrates_personaje_partidos.items():
            if data['jugados'] > 0:  # Solo incluir si hay partidos jugados
                stats['partidos']['por_personaje'][p.id][pers_id] = {
                    'ganados': data['ganados'],
                    'jugados': data['jugados'],
                    'winrate': (data['ganados'] / data['jugados'] * 100) if data['jugados'] > 0 else 0
                }

        # Guardar por personaje (partidos parciales) - NUEVA ESTADÍSTICA
        for pers_id, data in winrates_personaje_parcial.items():
            if data['jugados'] > 0:  # Solo incluir si hay partidos jugados
                stats['partidos']['por_personaje_parcial'][p.id][pers_id] = {
                    'ganados': data['ganados'],
                    'jugados': data['jugados'],
                    'winrate': (data['ganados'] / data['jugados'] * 100) if data['jugados'] > 0 else 0
                }

        # Guardar por personaje (rondas)
        for pers_id, data in winrates_personaje_rondas.items():
            if data['jugadas'] > 0:  # Solo incluir si hay rondas jugadas
                stats['rondas']['por_personaje'][p.id][pers_id] = {
                    'ganadas': data['ganadas'],
                    'jugadas': data['jugadas'],
                    'winrate': (data['ganadas'] / data['jugadas'] * 100) if data['jugadas'] > 0 else 0
                }

        # Guardar contra oponente (partidos)
        for op_id, data in winrates_vs_partidos.items():
            if data['jugados'] > 0:  # Solo incluir si hay partidos jugados
                stats['partidos']['contra_oponente'][p.id][op_id] = {
                    'ganados': data['ganados'],
                    'jugados': data['jugados'],
                    'winrate': (data['ganados'] / data['jugados'] * 100) if data['jugados'] > 0 else 0
                }

        # Guardar contra oponente (rondas)
        for op_id, data in winrates_vs_rondas.items():
            if data['jugadas'] > 0:  # Solo incluir si hay rondas jugadas
                stats['rondas']['contra_oponente'][p.id][op_id] = {
                    'ganadas': data['ganadas'],
                    'jugadas': data['jugadas'],
                    'winrate': (data['ganadas'] / data['jugadas'] * 100) if data['jugadas'] > 0 else 0
                }
        
        # Inicializar estructuras para torneos
        stats['torneos']['general'][p.id] = {'ganados': 0, 'jugados': 0, 'winrate': 0}
        stats['torneos']['por_personaje'][p.id] = {}
        stats['torneos']['por_personaje_parcial'][p.id] = {}
        stats['torneos']['contra_oponente'][p.id] = {}

        # Obtener resultados de torneos de este participante
        resultados = TorneoResultado.query.filter_by(participante_id=p.id).all()
        for res in resultados:
            torneo_id = res.torneo_id
            ranking = res.ranking
            stats['torneos']['general'][p.id]['jugados'] += 1
            if ranking == 1:
                stats['torneos']['general'][p.id]['ganados'] += 1

            data = torneos_data_cache.get(torneo_id)
            if not data:
                continue

            # Buscar el id del participante en los datos de la API
            participant_id_api = None
            for part in data.get('participant', []):
                if part and part.get('name') == p.nickname:
                    participant_id_api = part.get('id')
                    break
            if participant_id_api is None:
                continue

            # --- Estadísticas contra oponente (matches) ---
            for match in data.get('match', []):
                if match is None:
                    continue
                op1 = match.get('opponent1')
                op2 = match.get('opponent2')
                if not op1 or not op2:  # Si falta algún oponente, no se cuenta
                    continue
                if op1.get('id') == participant_id_api:
                    es_jugador1 = True
                    oponente_id_api = op2.get('id')
                elif op2.get('id') == participant_id_api:
                    es_jugador1 = False
                    oponente_id_api = op1.get('id')
                else:
                    continue

                # Obtener nombre del oponente
                oponente_nombre = None
                for part in data.get('participant', []):
                    if part and part.get('id') == oponente_id_api:
                        oponente_nombre = part.get('name')
                        break
                if not oponente_nombre:
                    continue
                oponente = Participante.query.filter_by(nickname=oponente_nombre).first()
                if not oponente:
                    continue

                result = op1.get('result') if es_jugador1 else op2.get('result')
                if result in ('win', 'loss'):
                    key = oponente.id
                    if key not in stats['torneos']['contra_oponente'][p.id]:
                        stats['torneos']['contra_oponente'][p.id][key] = {'ganados': 0, 'jugados': 0, 'winrate': 0}
                    stats['torneos']['contra_oponente'][p.id][key]['jugados'] += 1
                    if result == 'win':
                        stats['torneos']['contra_oponente'][p.id][key]['ganados'] += 1

            # --- Estadísticas por personaje: recolectar todos los juegos de este participante en el torneo ---
            juegos_participante = []

            # Matches sin hijos (child_count == 0)
            for match in data.get('match', []):
                if match is None or match.get('child_count', 0) != 0:
                    continue
                # Procesar opponent1
                op1 = match.get('opponent1')
                if op1 and op1.get('id') == participant_id_api:
                    personaje_id = op1.get('personaje')
                    result = op1.get('result')
                    juegos_participante.append({'personaje': personaje_id, 'result': result})
                # Procesar opponent2
                op2 = match.get('opponent2')
                if op2 and op2.get('id') == participant_id_api:
                    personaje_id = op2.get('personaje')
                    result = op2.get('result')
                    juegos_participante.append({'personaje': personaje_id, 'result': result})

            # Match games (para matches con hijos)
            for game in data.get('match_game', []):
                if game is None:
                    continue
                op1 = game.get('opponent1')
                op2 = game.get('opponent2')
                if op1 and op1.get('id') == participant_id_api:
                    personaje_id = op1.get('personaje')
                    result = op1.get('result')
                    juegos_participante.append({'personaje': personaje_id, 'result': result})
                if op2 and op2.get('id') == participant_id_api:
                    personaje_id = op2.get('personaje')
                    result = op2.get('result')
                    juegos_participante.append({'personaje': personaje_id, 'result': result})

            # Determinar si usó el mismo personaje en todos los juegos del torneo
            if juegos_participante:
                # Filtrar juegos sin personaje (pueden existir si no se registró)
                juegos_validos = [j for j in juegos_participante if j['personaje'] is not None]
                if juegos_validos:
                    primer_personaje = juegos_validos[0]['personaje']
                    mismo_personaje = all(j['personaje'] == primer_personaje for j in juegos_validos)
                    if mismo_personaje:
                        # Torneo completo para ese personaje
                        personaje_id = primer_personaje
                        if personaje_id not in stats['torneos']['por_personaje'][p.id]:
                            stats['torneos']['por_personaje'][p.id][personaje_id] = {'ganados': 0, 'jugados': 0, 'winrate': 0}
                        stats['torneos']['por_personaje'][p.id][personaje_id]['jugados'] += 1
                        # Si ganó el torneo, cuenta como victoria para ese personaje
                        if ranking == 1:
                            stats['torneos']['por_personaje'][p.id][personaje_id]['ganados'] += 1

                # Obtener personajes únicos usados en el torneo
                personajes_usados_torneo = set(j['personaje'] for j in juegos_validos)
                for personaje_id in personajes_usados_torneo:
                    if personaje_id not in stats['torneos']['por_personaje_parcial'][p.id]:
                        stats['torneos']['por_personaje_parcial'][p.id][personaje_id] = {'ganados': 0, 'jugados': 0, 'winrate': 0}
                    stats['torneos']['por_personaje_parcial'][p.id][personaje_id]['jugados'] += 1
                    if ranking == 1:
                        stats['torneos']['por_personaje_parcial'][p.id][personaje_id]['ganados'] += 1

        # Calcular winrates
        jugados = stats['torneos']['general'][p.id]['jugados']
        if jugados > 0:
            stats['torneos']['general'][p.id]['winrate'] = (stats['torneos']['general'][p.id]['ganados'] / jugados * 100)

        for pers_id, data in stats['torneos']['por_personaje'][p.id].items():
            if data['jugados'] > 0:
                data['winrate'] = (data['ganados'] / data['jugados'] * 100)

        for pers_id, data in stats['torneos']['por_personaje_parcial'][p.id].items():
            if data['jugados'] > 0:
                data['winrate'] = (data['ganados'] / data['jugados'] * 100)

        for op_id, data in stats['torneos']['contra_oponente'][p.id].items():
            if data['jugados'] > 0:
                data['winrate'] = (data['ganados'] / data['jugados'] * 100)

    return stats

def refrescar_matches_ronda(ronda):
    """
    Actualiza los matches de una ronda basándose en los asistentes actuales del evento.
    Mantiene los resultados de matches existentes si los jugadores siguen presentes.
    Retorna True si se completó sin errores, False en caso contrario.
    """

    try:
        asistentes = [a.participante for a in ronda.evento.asistencias]
        asistentes_ids = [p.id for p in asistentes]

        # Guardar temporalmente los matches existentes
        old_matches = {}
        for match in ronda.matches:
            key = (match.jugador1_id, match.jugador2_id)
            old_matches[key] = {
                'personaje1r1_id': match.personaje1r1_id,
                'personaje2r1_id': match.personaje2r1_id,
                'ganador_r1': match.ganador_r1,
                'personaje1r2_id': match.personaje1r2_id,
                'personaje2r2_id': match.personaje2r2_id,
                'ganador_r2': match.ganador_r2,
                'personaje1r3_id': match.personaje1r3_id,
                'personaje2r3_id': match.personaje2r3_id,
                'ganador_r3': match.ganador_r3,
                'personaje1r4_id': match.personaje1r4_id,
                'personaje2r4_id': match.personaje2r4_id,
                'ganador_r4': match.ganador_r4,
                'personaje1r5_id': match.personaje1r5_id,
                'personaje2r5_id': match.personaje2r5_id,
                'ganador_r5': match.ganador_r5,
                'ganador_match': match.ganador_match,
                'videos': match.videos
            }

        # Eliminar todos los matches de la ronda
        Match.query.filter_by(ronda_id=ronda.id).delete()

        # Generar nuevos matches
        matches_data = generar_round_robin(asistentes_ids)

        for match in matches_data:
            key = (match['jugador1_id'], match['jugador2_id'])
            new_match = Match(
                ronda_id=ronda.id,
                jugador1_id=match['jugador1_id'],
                jugador2_id=match['jugador2_id']
            )
            # Restaurar datos si existe match anterior
            if key in old_matches:
                old = old_matches[key]
                new_match.personaje1r1_id = old['personaje1r1_id']
                new_match.personaje2r1_id = old['personaje2r1_id']
                new_match.ganador_r1 = old['ganador_r1']
                new_match.personaje1r2_id = old['personaje1r2_id']
                new_match.personaje2r2_id = old['personaje2r2_id']
                new_match.ganador_r2 = old['ganador_r2']
                new_match.personaje1r3_id = old['personaje1r3_id']
                new_match.personaje2r3_id = old['personaje2r3_id']
                new_match.ganador_r3 = old['ganador_r3']
                new_match.personaje1r4_id = old['personaje1r4_id']
                new_match.personaje2r4_id = old['personaje2r4_id']
                new_match.ganador_r4 = old['ganador_r4']
                new_match.personaje1r5_id = old['personaje1r5_id']
                new_match.personaje2r5_id = old['personaje2r5_id']
                new_match.ganador_r5 = old['ganador_r5']
                new_match.ganador_match = old['ganador_match']
                new_match.videos = old['videos']
            db.session.add(new_match)

        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        # Registrar error si es necesario
        return False

def init_db(app):
    """Inicializar la base de datos"""
    with app.app_context():
        # Crear tablas
        db.create_all()
        app.logger.info("Tablas de la base de datos creadas")

        # --- Seed de personajes ---
        cantidad_personajes = Personaje.query.count()
        if cantidad_personajes < len(PERSONAJES):
            # Agregar personajes solo si la la cantidad de personajes es menor a la inicial
            count = seed_personajes()
            app.logger.info(f"Se agregaron {count} personajes a la base de datos")
        else:
            app.logger.info(f"Ya existen {cantidad_personajes} personajes en la base de datos. No se ejecutó seed_personajes.")
        
        # --- Seed de tipos de usuario ---
        cantidad_tipos = TipoUsuario.query.count()
        if cantidad_tipos < TIPOS_USUARIO.__len__():
            count = seed_tipos_usuario()
            app.logger.info(f"Se agregaron {count} tipos de usuario a la base de datos")
        else:
            app.logger.info(f"Ya existen {cantidad_tipos} tipos de usuario. No se ejecutó seed_tipos_usuario.")

        # --- Seed del Admin inicial ---
        seed_admin(app)
