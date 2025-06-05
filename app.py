import os
import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, url_for, flash
from dotenv import load_dotenv
from datetime import datetime, date 
from collections import defaultdict # Para agrupar no histórico

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "uma_chave_secreta_muito_forte_e_diferente_ainda_mais_segura")

# Configuração da Base de Dados
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
            conn.commit()
        print("Tabela 'medicamentos' verificada/criada com sucesso.")
    except psycopg2.Error as e:
        print(f"Erro ao inicializar a tabela 'medicamentos': {e}")
    finally:
        if conn:
            conn.close()

@app.template_filter('format_date_display')
def format_date_display_filter(date_obj):
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
    conn = get_db_connection()
    todos_medicamentos_nao_regulares = []
    if conn:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Modificação: Busca medicamentos que NÃO SÃO de uso regular.
                # Eles podem estar arquivados ou ter a data final passada.
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
    for med in todos_medicamentos_nao_regulares: # Agora iterando sobre a lista filtrada
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
    
    return render_template('historico.html', historico_agrupado=historico_agrupado)


@app.route('/add', methods=['POST'])
def add_medication():
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
    conn = get_db_connection()
    if not conn:
        flash("Não foi possível conectar à base de dados.", "error")
        return redirect(url_for('index'))

    editing_med = None
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur_get:
            # Apenas medicamentos não arquivados E (regulares OU com data final futura/nula) podem ser editados aqui
            # Esta lógica é para garantir que o formulário de edição só apareça para medicamentos "ativos" na lista principal
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
                """) # AND is_archived = FALSE para segurança adicional
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

    # Método GET
    if not editing_med: # Se não foi encontrado ou não cumpre os critérios para edição
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
def delete_medication(med_id): # Esta função agora ARQUIVA
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
