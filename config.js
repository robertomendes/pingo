// Configuração do Pingo. Sem estes valores o app funciona só no aparelho (sem conta).
// Preencha com os dados do projeto Supabase: Settings › API Keys.
// A chave pública (anon/publishable) pode ficar aqui: quem protege os dados é a
// Row Level Security do banco (supabase/schema.sql).
window.PINGO_CONFIG = {
  supabaseUrl: '',
  supabaseAnonKey: '',
  contato: '',
  regiao: 'São Paulo, Brasil'
};
