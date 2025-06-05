import os
import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, url_for, flash
from dotenv import load_dotenv
from datetime import datetime, date # Adicionado 'date'

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "uma_chave_secreta_muito_forte_e_diferente")

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
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_med_start_date ON medicamentos(start_date);")
            conn.commit()
        print("Tabela 'medicamentos' verificada/criada com sucesso.")
    except psycopg2.Error as e:
        print(f"Erro ao inicializar a tabela 'medicamentos': {e}")
    finally:
        if conn:
            conn.close()

@app.template_filter('format_date_display')
def format_date_display_filter(date_obj):
    """Formata um objeto date ou string de data para DD/MM/YYYY."""
    if not date_obj:
        return 'N/A'
    if isinstance(date_obj, str):
        try:
            # Tenta converter de YYYY-MM-DD para objeto date
            date_obj = datetime.strptime(date_obj, '%Y-%m-%d').date()
        except ValueError:
            return date_obj # Retorna a string original se não puder parsear
    if isinstance(date_obj, date): # Verifica se é um objeto date (ou datetime)
        return date_obj.strftime('%d/%m/%Y')
    return str(date_obj) # Fallback

@app.route('/')
def index():
    conn = get_db_connection()
    medicamentos_list = []
    show_form_on_load = request.args.get('show_form', False) # Para reabrir form após erro

    if conn:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM medicamentos ORDER BY created_at DESC")
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
                        INSERT INTO medicamentos (name, descricao, start_date, end_date, times, is_regular, quantity, form, unit)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """)
                    cur.execute(query, (name, descricao, start_date, end_date, times or None, is_regular, quantity, form_type, unit))
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

    editing_med = None # Inicializa para o escopo da função
    try: # Bloco try para buscar o medicamento para o GET
        with conn.cursor(cursor_factory=RealDictCursor) as cur_get:
            cur_get.execute("SELECT * FROM medicamentos WHERE id = %s", (str(med_id),))
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
            # Para manter o formulário preenchido em caso de erro no POST, precisamos re-renderizar
            # com os dados atuais do formulário (ou do 'editing_med' se não foram alterados).
            # No entanto, redirecionar para o GET é mais simples e comum.
            if conn: conn.close() # Fecha a conexão antes de redirecionar
            return redirect(url_for('edit_medication', med_id=med_id)) # Redireciona para o GET

        try:
            quantity = float(quantity_str) if quantity_str else 1.0
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None
        except ValueError:
            flash('Formato de data ou quantidade inválido.', 'error')
            if conn: conn.close()
            return redirect(url_for('edit_medication', med_id=med_id))

        try: # Bloco try para a query de UPDATE
            with conn.cursor() as cur_post:
                query = sql.SQL("""
                    UPDATE medicamentos 
                    SET name=%s, descricao=%s, start_date=%s, end_date=%s, times=%s, 
                        is_regular=%s, quantity=%s, form=%s, unit=%s, updated_at=NOW()
                    WHERE id=%s
                """)
                cur_post.execute(query, (name, descricao, start_date, end_date, times or None, is_regular, quantity, form_type, unit, med_id))
                conn.commit()
            flash('Medicamento atualizado com sucesso!', 'success')
        except psycopg2.Error as e:
            flash(f"Erro ao atualizar medicamento: {e}", "error")
        finally:
            if conn: conn.close()
        return redirect(url_for('index'))

    # Método GET: Carregar dados do medicamento para edição
    if not editing_med: # Se não foi encontrado no bloco try inicial
        flash('Medicamento não encontrado para edição.', 'error')
        if conn: conn.close()
        return redirect(url_for('index'))
    
    # Formata datas para o formulário HTML no GET
    if editing_med.get('start_date') and isinstance(editing_med.get('start_date'), (datetime, date)):
        editing_med['start_date'] = editing_med['start_date'].strftime('%Y-%m-%d')
    if editing_med.get('end_date') and isinstance(editing_med.get('end_date'), (datetime, date)):
        editing_med['end_date'] = editing_med['end_date'].strftime('%Y-%m-%d')
    if not editing_med.get('times'):
        editing_med['times'] = []
    
    # Busca todos os medicamentos para exibir na lista de fundo
    medicamentos_list_for_edit_page = []
    try:
        # Reabre a conexão se foi fechada ou usa a existente se ainda aberta e válida
        if conn.closed: conn = get_db_connection() 
        if conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur_list_edit:
                cur_list_edit.execute("SELECT * FROM medicamentos ORDER BY created_at DESC")
                medicamentos_list_for_edit_page = cur_list_edit.fetchall()
    except psycopg2.Error as e:
        print(f"Erro ao buscar lista de medicamentos para página de edição: {e}")
    finally:
        if conn: conn.close() # Fecha a conexão após buscar a lista

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
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM medicamentos WHERE id = %s", (str(med_id),))
                conn.commit()
            flash('Medicamento excluído com sucesso!', 'success')
        except psycopg2.Error as e:
            flash(f"Erro ao excluir medicamento: {e}", "error")
        finally:
            conn.close()
    else:
        flash("Não foi possível conectar à base de dados para excluir o medicamento.", "error")
    return redirect(url_for('index'))

if __name__ == '__main__':
    with app.app_context():
        init_db()
    # O Gunicorn será usado para iniciar a aplicação em produção (ver Dockerfile CMD)
    # Para desenvolvimento local, pode usar: app.run(host='0.0.0.0', port=5001, debug=True)
    # Mas como o Dockerfile agora usa `flask run`, não é estritamente necessário aqui.
