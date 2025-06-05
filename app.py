import os
import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response 
from dotenv import load_dotenv
from datetime import datetime, date, timedelta, time as time_obj 
from collections import defaultdict
import calendar
from ics import Calendar as ICSCalendar, Event as ICSEvent

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "uma_chave_secreta_muito_forte_e_diferente_ainda_mais_segura_com_calendario_ics_export_v2")

# Configuração da Base de Dados (como antes)
DB_HOST = os.getenv("DB_HOST", "postgres_db")
DB_NAME = os.getenv("DB_NAME", "medicamentos_db")
DB_USER = os.getenv("DB_USER", "user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "password")
DB_PORT = os.getenv("DB_PORT", "5432")

def get_db_connection():
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            port=DB_PORT
        )
        return conn
    except psycopg2.Error as e:
        print(f"Erro ao conectar ao PostgreSQL: {e}")
        return None

def init_db():
    # ... (função init_db como antes) ...
    conn = get_db_connection()
    if conn is None:
        print("Não foi possível inicializar a base de dados: conexão falhou.")
        return
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";")
            
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='medicamentos' AND column_name='is_archived';
            """)
            if not cur.fetchone():
                cur.execute("ALTER TABLE medicamentos ADD COLUMN is_archived BOOLEAN DEFAULT FALSE;")
                print("Coluna 'is_archived' adicionada à tabela 'medicamentos'.")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS medicamentos (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    name VARCHAR(255) NOT NULL,
                    descricao TEXT,
                    start_date DATE NOT NULL,
                    end_date DATE,
                    times TEXT[] DEFAULT '{}',
                    is_regular BOOLEAN DEFAULT FALSE,
                    quantity NUMERIC(10, 2) DEFAULT 1,
                    form VARCHAR(50) DEFAULT 'comprimido',
                    unit VARCHAR(50) DEFAULT 'unidade',
                    is_archived BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_med_start_date ON medicamentos(start_date);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_med_is_archived ON medicamentos(is_archived);")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS administracao_registos (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    medicamento_id UUID NOT NULL REFERENCES medicamentos(id) ON DELETE CASCADE,
                    data_dose DATE NOT NULL,
                    hora_dose TIME NOT NULL,
                    foi_administrado BOOLEAN DEFAULT FALSE,
                    administrado_em TIMESTAMP WITH TIME ZONE, 
                    CONSTRAINT unique_dose UNIQUE (medicamento_id, data_dose, hora_dose)
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_admin_data_hora ON administracao_registos(data_dose, hora_dose);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_admin_medicamento_id ON administracao_registos(medicamento_id);")
            
            conn.commit()
        print("Tabelas 'medicamentos' e 'administracao_registos' verificadas/criadas com sucesso.")
    except psycopg2.Error as e:
        print(f"Erro ao inicializar as tabelas: {e}")
    finally:
        if conn:
            conn.close()


@app.template_filter('format_date_display')
def format_date_display_filter(date_obj):
    # ... (função como antes) ...
    if not date_obj: return 'N/A'
    if isinstance(date_obj, str):
        try:
            date_obj = datetime.strptime(date_obj, '%Y-%m-%d').date()
        except ValueError:
            try:
                date_obj = datetime.fromisoformat(date_obj.replace('Z', '+00:00')).date()
            except ValueError:
                 return date_obj 
    if isinstance(date_obj, date):
        return date_obj.strftime('%d/%m/%Y')
    return str(date_obj)

@app.route('/')
def index():
    # ... (rota index como antes) ...
    conn = get_db_connection()
    medicamentos_list = []
    show_form_on_load = request.args.get('show_form', False) 

    if conn:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = sql.SQL("""
                    SELECT * FROM medicamentos 
                    WHERE is_archived = FALSE AND 
                          (is_regular = TRUE OR end_date IS NULL OR end_date >= CURRENT_DATE)
                    ORDER BY created_at DESC
                """)
                cur.execute(query)
                medicamentos_list = cur.fetchall()
        except psycopg2.Error as e:
            flash(f"Erro ao buscar medicamentos: {e}", "error")
        finally:
            conn.close()
    else:
        flash("Não foi possível conectar à base de dados para buscar medicamentos.", "error")
    
    grouped_medications = {}
    for med in medicamentos_list:
        times_for_med = med.get('times') if med.get('times') else ["Sem Horário Definido"]
        for t in times_for_med:
            display_time = t if t == "Sem Horário Definido" else t
            if display_time not in grouped_medications:
                grouped_medications[display_time] = []
            grouped_medications[display_time].append(med)
    
    sorted_times = sorted(grouped_medications.keys(), key=lambda x: (x == "Sem Horário Definido", x))
    ordered_grouped_medications = {time: grouped_medications[time] for time in sorted_times}

    return render_template('index.html', 
                           grouped_medications=ordered_grouped_medications, 
                           editing_med=None,
                           show_form_on_load=show_form_on_load)


@app.route('/historico')
def historico():
    # ... (rota historico como antes) ...
    conn = get_db_connection()
    todos_medicamentos_nao_regulares = []
    if conn:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = sql.SQL("""
                    SELECT * FROM medicamentos 
                    WHERE is_regular = FALSE 
                    ORDER BY start_date DESC, name ASC
                """)
                cur.execute(query)
                todos_medicamentos_nao_regulares = cur.fetchall()
        except psycopg2.Error as e:
            flash(f"Erro ao buscar histórico de medicamentos: {e}", "error")
        finally:
            conn.close()
    else:
        flash("Não foi possível conectar à base de dados para buscar o histórico.", "error")

    historico_agrupado = defaultdict(list)
    for med in todos_medicamentos_nao_regulares: 
        if med.get('start_date'):
            start_dt = med['start_date']
            if isinstance(start_dt, str):
                try:
                    start_dt = datetime.strptime(start_dt, '%Y-%m-%d').date()
                except ValueError: 
                    try:
                         start_dt = datetime.fromisoformat(start_dt.replace('Z', '+00:00')).date()
                    except ValueError:
                        continue
            
            if isinstance(start_dt, date):
                mes_ano_key = start_dt.strftime("%B %Y").capitalize()
                historico_agrupado[mes_ano_key].append(med)
    
    return render_template('historico.html', 
                           historico_agrupado=historico_agrupado,
                           today_date=date.today())


# --- ROTAS PARA CALENDÁRIO ---
@app.route('/calendario/')
@app.route('/calendario/<int:year>/<int:month>')
def calendario_view(year=None, month=None):
    # ... (rota calendario_view como antes, incluindo a lógica para medicamentos_por_dia_para_json) ...
    today = date.today() 
    if year is None or month is None:
        year = today.year
        month = today.month
    else:
        try:
            if not (1 <= month <= 12):
                flash("Mês inválido.", "error")
                return redirect(url_for('calendario_view'))
        except ValueError:
            flash("Data inválida para o calendário.", "error")
            return redirect(url_for('calendario_view'))

    cal = calendar.Calendar()
    month_days_dates = cal.monthdatescalendar(year, month)

    conn = get_db_connection()
    active_meds_for_calendar = []
    administracao_data_raw = {}

    if conn:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                first_day_of_month = date(year, month, 1)
                start_display_date = month_days_dates[0][0]
                end_display_date = month_days_dates[-1][-1]

                query_meds = sql.SQL("""
                    SELECT id, name, times, start_date, end_date, is_regular, descricao 
                    FROM medicamentos 
                    WHERE is_archived = FALSE AND 
                          (is_regular = TRUE OR 
                           (start_date <= %s AND (end_date IS NULL OR end_date >= %s)))
                """)
                cur.execute(query_meds, (end_display_date, start_display_date))
                active_meds_for_calendar = cur.fetchall()

                query_admin = sql.SQL("""
                    SELECT medicamento_id, data_dose, hora_dose, foi_administrado 
                    FROM administracao_registos
                    WHERE data_dose BETWEEN %s AND %s
                """)
                cur.execute(query_admin, (start_display_date, end_display_date))
                for row in cur.fetchall():
                    hora_dose_str_key = row['hora_dose'].strftime('%H:%M')
                    key = (str(row['medicamento_id']), row['data_dose'].strftime('%Y-%m-%d'), hora_dose_str_key)
                    administracao_data_raw[key] = row['foi_administrado']
        except psycopg2.Error as e:
            flash(f"Erro ao buscar dados para o calendário: {e}", "error")
        finally:
            conn.close()
    else:
        flash("Não foi possível conectar à base de dados para o calendário.", "error")

    medicamentos_por_dia_para_json = defaultdict(list)

    for week_idx, week in enumerate(month_days_dates):
        for day_idx, day_date_obj in enumerate(week):
            day_str = day_date_obj.strftime('%Y-%m-%d')
            doses_do_dia_com_time_obj = [] 
            for med in active_meds_for_calendar:
                med_start_date = med['start_date']
                med_end_date = med['end_date']
                
                is_active_today = False
                if med_start_date <= day_date_obj:
                    if med['is_regular'] or med_end_date is None or med_end_date >= day_date_obj:
                        is_active_today = True
                
                if is_active_today and med.get('times'):
                    for time_str in med['times']: 
                        if not time_str: continue

                        admin_key = (str(med['id']), day_str, time_str) 
                        is_administered = administracao_data_raw.get(admin_key, False)
                        
                        try:
                            hora_obj_para_ordenar = datetime.strptime(time_str, '%H:%M').time()
                        except ValueError:
                            print(f"AVISO: Formato de hora inválido '{time_str}' para medicamento '{med['name']}'. Pulando este horário.")
                            continue

                        doses_do_dia_com_time_obj.append({
                            "med_id": str(med['id']),
                            "nome": med['name'],
                            "hora_str": time_str, 
                            "hora_obj": hora_obj_para_ordenar, 
                            "is_administered": is_administered,
                            "descricao": med.get('descricao')
                        })
            
            if doses_do_dia_com_time_obj:
                doses_ordenadas_com_time_obj = sorted(doses_do_dia_com_time_obj, key=lambda x: x['hora_obj'])
                doses_para_json = []
                for dose_ordenada in doses_ordenadas_com_time_obj:
                    doses_para_json.append({
                        "med_id": dose_ordenada["med_id"],
                        "nome": dose_ordenada["nome"],
                        "hora_str": dose_ordenada["hora_str"],
                        "is_administered": dose_ordenada["is_administered"],
                        "descricao": dose_ordenada.get("descricao")
                    })
                medicamentos_por_dia_para_json[day_str] = doses_para_json

    current_date_nav = date(year, month, 1)
    prev_month_date_nav = (current_date_nav.replace(day=1) - timedelta(days=1)).replace(day=1)
    next_month_date_nav = (current_date_nav.replace(day=28) + timedelta(days=4)).replace(day=1)

    nav = {
        "current_month_display": current_date_nav.strftime("%B %Y").capitalize(),
        "prev_year": prev_month_date_nav.year,
        "prev_month": prev_month_date_nav.month,
        "next_year": next_month_date_nav.year,
        "next_month": next_month_date_nav.month,
        "today_str": today.strftime('%Y-%m-%d')
    }
    
    return render_template('calendario.html', 
                           month_days_dates=month_days_dates,
                           year=year, 
                           month=month,
                           medicamentos_por_dia=medicamentos_por_dia_para_json, 
                           nav=nav,
                           today_date=today)

@app.route('/calendario/exportar_ics/<int:year>/<int:month>')
def exportar_calendario_ics(year, month):
    cal_ics = ICSCalendar()
    conn = get_db_connection()
    if not conn:
        flash("Erro ao conectar à base de dados para exportação.", "error")
        return redirect(url_for('calendario_view', year=year, month=month))

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            first_day_of_month = date(year, month, 1)
            if month == 12:
                last_day_of_month = date(year, month, 31)
            else:
                last_day_of_month = date(year, month + 1, 1) - timedelta(days=1)

            query_meds = sql.SQL("""
                SELECT id, name, times, start_date, end_date, is_regular, descricao
                FROM medicamentos 
                WHERE is_archived = FALSE AND 
                      (is_regular = TRUE OR 
                       (start_date <= %s AND (end_date IS NULL OR end_date >= %s)))
            """)
            cur.execute(query_meds, (last_day_of_month, first_day_of_month))
            medicamentos_do_mes = cur.fetchall()

            current_date_iter = first_day_of_month # Renomeada para evitar conflito de nome
            while current_date_iter <= last_day_of_month:
                for med in medicamentos_do_mes:
                    med_start = med['start_date']
                    med_end = med['end_date']
                    is_active_this_day = False
                    if med_start <= current_date_iter:
                        if med['is_regular'] or med_end is None or med_end >= current_date_iter:
                            is_active_this_day = True
                    
                    if is_active_this_day and med.get('times'):
                        for time_str in med['times']: 
                            if not time_str: continue
                            try:
                                hour, minute = map(int, time_str.split(':'))
                                event_start_dt = datetime.combine(current_date_iter, time_obj(hour, minute))
                                
                                event = ICSEvent()
                                event.name = f"Tomar: {med['name']}"
                                event.begin = event_start_dt
                                event.duration = timedelta(minutes=15) 
                                if med.get('descricao'):
                                    event.description = med.get('descricao')
                                cal_ics.events.add(event)
                            except ValueError:
                                print(f"Skipping invalid time format for ICS: {time_str} for med {med['name']}")
                current_date_iter += timedelta(days=1)
        
        # CORREÇÃO AQUI: Usar o método serialize()
        ics_content = cal_ics.serialize() 
        response = Response(ics_content, mimetype="text/calendar")
        response.headers["Content-Disposition"] = f"attachment; filename=medicamentos_{year}_{month:02d}.ics"
        return response

    except psycopg2.Error as e:
        flash(f"Erro ao gerar ficheiro ICS: {e}", "error")
        return redirect(url_for('calendario_view', year=year, month=month))
    finally:
        if conn:
            conn.close()


@app.route('/api/marcar_administrado', methods=['POST'])
def marcar_administrado():
    # ... (rota como antes) ...
    data = request.get_json()
    medicamento_id = data.get('medicamento_id')
    data_dose_str = data.get('data_dose') 
    hora_dose_str = data.get('hora_dose') 
    foi_administrado = data.get('foi_administrado', False)

    if not all([medicamento_id, data_dose_str, hora_dose_str]):
        return jsonify({"success": False, "message": "Dados incompletos."}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"success": False, "message": "Erro de conexão com a base de dados."}), 500

    try:
        data_dose = datetime.strptime(data_dose_str, '%Y-%m-%d').date()
        hora_dose_obj = datetime.strptime(hora_dose_str, '%H:%M').time() 

        with conn.cursor() as cur:
            query = sql.SQL("""
                INSERT INTO administracao_registos (medicamento_id, data_dose, hora_dose, foi_administrado, administrado_em)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (medicamento_id, data_dose, hora_dose) 
                DO UPDATE SET 
                    foi_administrado = EXCLUDED.foi_administrado,
                    administrado_em = EXCLUDED.administrado_em
                RETURNING id; 
            """)
            administrado_em_val = datetime.now() if foi_administrado else None
            cur.execute(query, (medicamento_id, data_dose, hora_dose_obj, foi_administrado, administrado_em_val))
            result = cur.fetchone()
            conn.commit()

            if result:
                return jsonify({"success": True, "message": "Status de administração atualizado."})
            else:
                 return jsonify({"success": True, "message": "Status de administração processado." })
    except ValueError:
        return jsonify({"success": False, "message": "Formato de data ou hora inválido."}), 400
    except psycopg2.Error as e:
        print(f"Erro na API marcar_administrado: {e}")
        return jsonify({"success": False, "message": f"Erro na base de dados: {e}"}), 500
    finally:
        if conn:
            conn.close()
    return jsonify({"success": False, "message": "Erro desconhecido."}), 500


# ... (rotas add_medication, edit_medication, delete_medication como antes) ...
@app.route('/add', methods=['POST'])
def add_medication():
    # ... (código como antes) ...
    if request.method == 'POST':
        name = request.form.get('name')
        descricao = request.form.get('descricao')
        start_date_str = request.form.get('startDate')
        end_date_str = request.form.get('endDate')
        times = [t for t in request.form.getlist('times[]') if t] 
        is_regular = 'isRegular' in request.form
        quantity_str = request.form.get('quantity', '1')
        form_type = request.form.get('formType', 'comprimido')
        unit = request.form.get('unit', 'unidade')
        is_archived = False 

        if not name or not start_date_str:
            flash('Nome e Data de Início são obrigatórios!', 'error')
            return redirect(url_for('index', show_form=True))

        try:
            quantity = float(quantity_str) if quantity_str else 1.0
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None
        except ValueError:
            flash('Formato de data ou quantidade inválido.', 'error')
            return redirect(url_for('index', show_form=True))

        conn = get_db_connection()
        if conn:
            try:
                with conn.cursor() as cur:
                    query = sql.SQL("""
                        INSERT INTO medicamentos (name, descricao, start_date, end_date, times, is_regular, quantity, form, unit, is_archived)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """)
                    cur.execute(query, (name, descricao, start_date, end_date, times or None, is_regular, quantity, form_type, unit, is_archived))
                    conn.commit()
                flash('Medicamento adicionado com sucesso!', 'success')
            except psycopg2.Error as e:
                flash(f"Erro ao adicionar medicamento: {e}", "error")
            finally:
                conn.close()
        else:
            flash("Não foi possível conectar à base de dados para adicionar o medicamento.", "error")
            
    return redirect(url_for('index'))

@app.route('/edit/<uuid:med_id>', methods=['GET', 'POST'])
def edit_medication(med_id):
    # ... (código como antes) ...
    conn = get_db_connection()
    if not conn:
        flash("Não foi possível conectar à base de dados.", "error")
        return redirect(url_for('index'))

    editing_med = None
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur_get:
            query_get_med = sql.SQL("""
                SELECT * FROM medicamentos 
                WHERE id = %s AND is_archived = FALSE AND
                      (is_regular = TRUE OR end_date IS NULL OR end_date >= CURRENT_DATE)
            """)
            cur_get.execute(query_get_med, (str(med_id),))
            editing_med = cur_get.fetchone()
    except psycopg2.Error as e:
        flash(f"Erro ao buscar dados para edição: {e}", "error")
        if conn: conn.close()
        return redirect(url_for('index'))

    if request.method == 'POST':
        name = request.form.get('name')
        descricao = request.form.get('descricao')
        start_date_str = request.form.get('startDate')
        end_date_str = request.form.get('endDate')
        times = [t for t in request.form.getlist('times[]') if t]
        is_regular = 'isRegular' in request.form
        quantity_str = request.form.get('quantity')
        form_type = request.form.get('formType')
        unit = request.form.get('unit')

        if not name or not start_date_str:
            flash('Nome e Data de Início são obrigatórios!', 'error')
            if conn: conn.close()
            return redirect(url_for('edit_medication', med_id=med_id))

        try:
            quantity = float(quantity_str) if quantity_str else 1.0
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None
        except ValueError:
            flash('Formato de data ou quantidade inválido.', 'error')
            if conn: conn.close()
            return redirect(url_for('edit_medication', med_id=med_id))

        try:
            with conn.cursor() as cur_post:
                query_update = sql.SQL("""
                    UPDATE medicamentos 
                    SET name=%s, descricao=%s, start_date=%s, end_date=%s, times=%s, 
                        is_regular=%s, quantity=%s, form=%s, unit=%s, updated_at=NOW()
                    WHERE id=%s AND is_archived = FALSE 
                """)
                cur_post.execute(query_update, (name, descricao, start_date, end_date, times or None, is_regular, quantity, form_type, unit, med_id))
                conn.commit()
                if cur_post.rowcount == 0:
                     flash('Medicamento não encontrado para atualização ou já arquivado.', 'warning')
                else:
                    flash('Medicamento atualizado com sucesso!', 'success')
        except psycopg2.Error as e:
            flash(f"Erro ao atualizar medicamento: {e}", "error")
        finally:
            if conn: conn.close()
        return redirect(url_for('index'))

    if not editing_med:
        flash('Medicamento não disponível para edição (pode estar arquivado ou ter data final passada e não ser regular).', 'warning')
        if conn: conn.close()
        return redirect(url_for('index'))
    
    if editing_med.get('start_date') and isinstance(editing_med.get('start_date'), (datetime, date)):
        editing_med['start_date'] = editing_med['start_date'].strftime('%Y-%m-%d')
    if editing_med.get('end_date') and isinstance(editing_med.get('end_date'), (datetime, date)):
        editing_med['end_date'] = editing_med['end_date'].strftime('%Y-%m-%d')
    if not editing_med.get('times'):
        editing_med['times'] = []
    
    medicamentos_list_for_edit_page = [] 
    try:
        if conn.closed: conn = get_db_connection() 
        if conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur_list_edit:
                query_list = sql.SQL("""
                    SELECT * FROM medicamentos 
                    WHERE is_archived = FALSE AND 
                          (is_regular = TRUE OR end_date IS NULL OR end_date >= CURRENT_DATE)
                    ORDER BY created_at DESC
                """)
                cur_list_edit.execute(query_list)
                medicamentos_list_for_edit_page = cur_list_edit.fetchall()
    except psycopg2.Error as e:
        print(f"Erro ao buscar lista de medicamentos para página de edição: {e}")
    finally:
        if conn: conn.close()

    grouped_medications_for_edit_page = {}
    for med_item in medicamentos_list_for_edit_page:
        times_for_med_item = med_item.get('times') if med_item.get('times') else ["Sem Horário Definido"]
        for t_item in times_for_med_item:
            display_time_item = t_item if t_item == "Sem Horário Definido" else t_item
            if display_time_item not in grouped_medications_for_edit_page:
                grouped_medications_for_edit_page[display_time_item] = []
            grouped_medications_for_edit_page[display_time_item].append(med_item)
            
    sorted_times_for_edit_page = sorted(grouped_medications_for_edit_page.keys(), key=lambda x: (x == "Sem Horário Definido", x))
    ordered_grouped_medications_for_edit_page = {time: grouped_medications_for_edit_page[time] for time in sorted_times_for_edit_page}
    
    return render_template('index.html', 
                           grouped_medications=ordered_grouped_medications_for_edit_page, 
                           editing_med=editing_med, 
                           show_form_on_load=True)


@app.route('/delete/<uuid:med_id>', methods=['POST']) 
def delete_medication(med_id):
    # ... (código como antes) ...
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("UPDATE medicamentos SET is_archived = TRUE, updated_at = NOW() WHERE id = %s", (str(med_id),))
                conn.commit()
                if cur.rowcount == 0:
                    flash('Medicamento não encontrado.', 'warning')
                else:
                    flash('Medicamento movido para o histórico (arquivado).', 'success')
        except psycopg2.Error as e:
            flash(f"Erro ao arquivar medicamento: {e}", "error")
        finally:
            conn.close()
    else:
        flash("Não foi possível conectar à base de dados para arquivar o medicamento.", "error")
    return redirect(url_for('index'))

if __name__ == '__main__':
    with app.app_context():
        init_db()

