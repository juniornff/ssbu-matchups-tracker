from collections import defaultdict, deque
from models import db, Participante, Personaje, Evento, Asistencia, Ronda, Torneo, TorneoResultado, Match
import random
import requests
import json
from flask import current_app


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

def obtener_Codigo_Secreto():
    try:
        with open('pass.txt', 'r') as f:
            Codigo_Secreto = f.read().strip()
        if not Codigo_Secreto:
            raise ValueError("El archivo pass.txt está vacío")
    except FileNotFoundError:
        app.logger.info("ERROR: No se encontró el archivo pass.txt")
        app.logger.info("Por favor crea un archivo pass.txt con el código secreto")
        exit(1)
    except Exception as e:
        app.logger.info(f"ERROR leyendo pass.txt: {str(e)}")
        exit(1)
    return Codigo_Secreto

# Función común para actualizar personajes
def actualizar_personajes_participantes_logic(app):

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

def obtener_standings_torneo(torneo, api_url):
    """
    Obtiene los standings de un torneo desde la API.
    Retorna un diccionario con los datos si éxito, o un dict con 'error'.
    Además, guarda los resultados en la base de datos si no existen.
    """
    stage_id = torneo.torneo_id_externo
    try:
        response = requests.get(f"{api_url}/tournaments/{stage_id}/standings")
        if response.status_code == 200:
            standings_data = response.json()
            # Guardar en BD si no existen resultados
            resultados_existentes = TorneoResultado.query.filter_by(torneo_id=torneo.id).count()
            if resultados_existentes == 0 and 'standings' in standings_data:
                for item in standings_data['standings']:
                    participante = Participante.query.filter_by(nickname=item['name']).first()
                    if participante:
                        resultado = TorneoResultado(
                            torneo_id=torneo.id,
                            participante_id=participante.id,
                            ranking=item['rank']
                        )
                        db.session.add(resultado)
                db.session.commit()
            return standings_data
        else:
            if response.status_code == 404:
                return {'error': 'No disponible (torneo no encontrado)'}
            if response.status_code == 500:
                return {'error': 'No disponible (Completar todos los partidos del torneo)'}
    except requests.exceptions.ConnectionError:
        return {'error': 'Error de conexión con la API'}
    except requests.exceptions.Timeout:
        return {'error': 'Tiempo de espera agotado'}
    except requests.exceptions.RequestException as e:
        return {'error': f'Error: {str(e)}'}

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

def calcular_winrates(participantes, personajes):
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
        }
    }

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

        # Verificar si ya existen personajes en la base de datos
        from models import Personaje
        cantidad_personajes = Personaje.query.count()

        if cantidad_personajes < len(PERSONAJES):
            # Agregar personajes solo si la la cantidad de personajes es menor a la inicial
            count = seed_personajes()
            app.logger.info(f"Se agregaron {count} personajes a la base de datos")
        else:
            app.logger.info(f"Ya existen {cantidad_personajes} personajes en la base de datos. No se ejecutó seed_personajes.")
