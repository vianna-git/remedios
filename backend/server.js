// server.js (Backend com campo Descrição)
const express = require('express');
const cors = require('cors');
const { Pool } = require('pg');

const app = express();
const port = process.env.PORT || 5000;

app.use(cors());
app.use(express.json());

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
});

pool.connect((err, client, release) => {
  if (err) {
    return console.error('Erro ao adquirir cliente da pool de conexão', err.stack);
  }
  client.query('SELECT NOW()', (err, result) => {
    release();
    if (err) {
      return console.error('Erro ao executar query de teste', err.stack);
    }
    console.log('Conexão com PostgreSQL bem-sucedida:', result.rows[0].now);
  });
});

// GET /medicamentos
app.get('/medicamentos', async (req, res) => {
  try {
    const result = await pool.query('SELECT * FROM medicamentos ORDER BY created_at DESC');
    res.json(result.rows);
  } catch (err) {
    console.error('Erro ao buscar medicamentos:', err.message, err.stack);
    res.status(500).json({ message: 'Erro ao buscar medicamentos no servidor.', error: err.message });
  }
});

// GET /medicamentos/:id
app.get('/medicamentos/:id', async (req, res) => {
  const { id } = req.params;
  try {
    const result = await pool.query('SELECT * FROM medicamentos WHERE id = $1', [id]);
    if (result.rows.length === 0) {
      return res.status(404).json({ message: 'Medicamento não encontrado.' });
    }
    res.json(result.rows[0]);
  } catch (err) {
    console.error(`Erro ao buscar medicamento ${id}:`, err.message, err.stack);
    res.status(500).json({ message: 'Erro ao buscar medicamento no servidor.', error: err.message });
  }
});

// POST /medicamentos
app.post('/medicamentos', async (req, res) => {
  const { name, descricao, startDate, endDate, times, isRegular, quantity, form, unit } = req.body; // Adicionado descricao
  if (!name || !startDate) {
    return res.status(400).json({ message: 'Nome e data de início são obrigatórios.' });
  }
  try {
    const queryText = `
      INSERT INTO medicamentos (name, descricao, start_date, end_date, times, is_regular, quantity, form, unit, created_at, updated_at)
      VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW(), NOW())
      RETURNING *;
    `;
    const values = [name, descricao || null, startDate, endDate || null, times || [], isRegular || false, quantity || 1, form || 'comprimido', unit || 'unidade'];
    const result = await pool.query(queryText, values);
    res.status(201).json(result.rows[0]);
  } catch (err) {
    console.error('Erro ao adicionar medicamento:', err.message, err.stack);
    res.status(500).json({ message: 'Erro ao adicionar medicamento no servidor.', error: err.message });
  }
});

// PUT /medicamentos/:id
app.put('/medicamentos/:id', async (req, res) => {
  const { id } = req.params;
  const { name, descricao, startDate, endDate, times, isRegular, quantity, form, unit } = req.body; // Adicionado descricao
  try {
    const queryText = `
      UPDATE medicamentos
      SET name = $1, descricao = $2, start_date = $3, end_date = $4, times = $5, is_regular = $6, quantity = $7, form = $8, unit = $9, updated_at = NOW()
      WHERE id = $10
      RETURNING *;
    `;
    const values = [name, descricao || null, startDate, endDate || null, times || [], isRegular || false, quantity || 1, form || 'comprimido', unit || 'unidade', id];
    const result = await pool.query(queryText, values);
    if (result.rows.length === 0) {
      return res.status(404).json({ message: 'Medicamento não encontrado para atualização.' });
    }
    res.json(result.rows[0]);
  } catch (err) {
    console.error(`Erro ao atualizar medicamento ${id}:`, err.message, err.stack);
    res.status(500).json({ message: 'Erro ao atualizar medicamento no servidor.', error: err.message });
  }
});

// DELETE /medicamentos/:id
app.delete('/medicamentos/:id', async (req, res) => {
  const { id } = req.params;
  try {
    const result = await pool.query('DELETE FROM medicamentos WHERE id = $1 RETURNING *', [id]);
    if (result.rowCount === 0) {
      return res.status(404).json({ message: 'Medicamento não encontrado para exclusão.' });
    }
    res.status(200).json({ message: 'Medicamento excluído com sucesso.', deletedMedication: result.rows[0]});
  } catch (err) {
    console.error(`Erro ao excluir medicamento ${id}:`, err.message, err.stack);
    res.status(500).json({ message: 'Erro ao excluir medicamento no servidor.', error: err.message });
  }
});

app.get('/health', (req, res) => {
  res.status(200).json({ status: 'UP', message: 'Backend API está funcionando!' });
});

app.use((req, res, next) => {
  res.status(404).json({ message: "Desculpe, essa rota não existe no backend." });
});

app.use((err, req, res, next) => {
  console.error("Erro não tratado no servidor:", err.stack);
  res.status(500).json({ message: "Ocorreu um erro inesperado no servidor." });
});

app.listen(port, () => {
  console.log(`Servidor backend rodando na porta ${port}`);
  console.log(`DATABASE_URL: ${process.env.DATABASE_URL ? 'Configurada' : 'NÃO CONFIGURADA!'}`);
});

/*
SQL para criar/atualizar a tabela 'medicamentos' (execute na base de dados 'medicationsdb'):

-- Primeiro, adicione a coluna se ela não existir (para atualizações)
ALTER TABLE medicamentos ADD COLUMN IF NOT EXISTS descricao TEXT;

-- Depois, crie a tabela se ela não existir (para primeira execução)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS medicamentos (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    descricao TEXT, -- Nova coluna
    start_date DATE NOT NULL,
    end_date DATE,
    times TEXT[],
    is_regular BOOLEAN DEFAULT FALSE,
    quantity NUMERIC(10, 2) DEFAULT 1,
    form VARCHAR(50) DEFAULT 'comprimido',
    unit VARCHAR(50) DEFAULT 'unidade',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Recriar índice se necessário, ou criar se não existir
DROP INDEX IF EXISTS idx_med_start_date; -- Opcional, se quiser garantir que não há conflito
CREATE INDEX IF NOT EXISTS idx_med_start_date ON medicamentos(start_date);
*/
