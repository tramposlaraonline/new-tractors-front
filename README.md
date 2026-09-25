# New Tractors — Front-end (app Django)

Reconstrução do front-end do new-tractors.com a partir do HTML salvo do login + prints.

## Encaixar no projeto Django

1. Copie a pasta `frontend/` para a raiz do projeto.
2. `settings.py`:
   ```python
   INSTALLED_APPS += ["frontend"]
   LOGIN_URL = "frontend:login"
   LOGIN_REDIRECT_URL = "/"          # para onde o modal "Acesso Autorizado!" redireciona
   ```
   `TEMPLATES[0]["APP_DIRS"]` precisa ser `True` (padrão do `startproject`).
3. `urls.py` do projeto:
   ```python
   path("", include("frontend.urls")),
   ```
   Rotas criadas (iguais às do site original): `/login`, `/reg`, `/forgot_password`.
   Área logada (mesmos paths do site): `/` (Início), `/equipe`, `/recharge` (depósito), `/record` (compras),
   `/my` (perfil), `/withdraw` (saque). O Extrato é um modal (não tem URL própria). Como o app ocupa a raiz `/`,
   ele tem que ser o dono dessa rota no projeto.
5. Opcional: `FRONTEND_SUPPORT_URL = "https://wa.me/55..."` no `settings.py` — destino do botão "Chat"
   e do fone do cabeçalho (abrem em nova aba). Sem essa setting, os botões aparecem mas não fazem nada.
6. Dados reais (ver `frontend/providers.py`), cada um é o caminho de uma função `f(user) -> dict`:
   - `FRONTEND_WALLET_PROVIDER` → `{"invest_balance": Decimal, "withdraw_balance": Decimal}`
     (card "Meu Patrimônio"; o total é a soma dos dois). Sem a setting, tudo aparece como R$ 0,00.
   - `FRONTEND_HEADER_PROVIDER` → `{"has_unread_notifications": bool}` (ponto dourado no sino).
   - `FRONTEND_CHECKIN_PROVIDER` → `{"done_today": bool}`; `FRONTEND_ROULETTE_PROVIDER` → `{"spins_available": int}`;
     `FRONTEND_PRODUCTS_PROVIDER` → lista de máquinas (padrão: as 12 de `frontend/catalog.py`).
   - Ações (POST + JSON, rotas `/acoes/...`), cada uma devolve `{"ok": bool, "message"?: str, ...}`:
     `FRONTEND_CHECKIN_ACTION(user)`, `FRONTEND_BONUS_ACTION(user, code)` → `amount`,
     `FRONTEND_ROULETTE_ACTION(user)` → `prize_amount`, `segment_index` (0–6, fatia onde a roleta para),
     `FRONTEND_PURCHASE_ACTION(user, product_id, idempotency_key)` → `spins_awarded`.
     **A função do projeto garante saldo, uso único do bônus, limite de giros e idempotência da compra**
     (a mesma `idempotency_key` nunca cobra duas vezes). Sem a setting, a ação responde "Função indisponível".
   - Saque Pix (/withdraw): `FRONTEND_WITHDRAW_PROVIDER(user)` → chave Pix, taxa, mínimo, prazo e saques recentes;
     `FRONTEND_WITHDRAW_ACTION(user, amount, idempotency_key)` → `{"ok", "message"?}`. A view já recusa valor inválido,
     abaixo do mínimo, acima do saldo e sem chave Pix, **mas o backend precisa debitar de forma atômica, bloquear
     saque simultâneo e não repetir a mesma idempotency_key** (a checagem da view não protege contra corrida).
   - Depósito Pix (`/recharge` e pagamento em `/recharge/<id>`): `FRONTEND_DEPOSIT_PROVIDER` (mínimo, máximo, valores
     rápidos, CPF cadastrado), `FRONTEND_DEPOSIT_CHARGE_PROVIDER(user, charge_id)` (**tem que filtrar pelo usuário**),
     `FRONTEND_CPF_ACTION`, `FRONTEND_DEPOSIT_ACTION` (→ `charge_id`), `FRONTEND_DEPOSIT_STATUS(user, charge_id,
     manual_check)` (consultado a cada 5s e no botão "Já fiz o Pix"). O saldo só deve ser creditado pelo webhook
     do provedor Pix — o botão apenas pede uma nova consulta.
   - Minhas Compras (`/record`): `FRONTEND_PURCHASES_PROVIDER(user)` → lista de contratos (id, produto, valor, crédito
     diário, início, término, lucro acumulado, próximo crédito, status). Totais calculados só com os ativos.
   - Equipe (`/equipe`, `?aba=metas` abre direto em Metas): `FRONTEND_TEAM_PROVIDER(user)` → código de convite,
     comissões, níveis, membros e metas (formato em `frontend/providers.py`). Totais, taxa de ativação, barras e
     "Faltam..." são calculados no front. O link de convite é `/reg?code=<código>`.
   - Extrato (modal): `FRONTEND_STATEMENT_PROVIDER(user, kinds, offset, limit)` → lançamentos do mais novo para o mais
     antigo (ver `frontend/statement.py`). `kinds` vem do filtro escolhido; filtrar e paginar no banco.
   - Chave Pix de saque: `FRONTEND_PIX_KEY_ACTION(user, key_type, key)` — tipos cpf, cnpj, phone, email, random.
     Titular e documento vêm do cadastro; o backend deve recusar chave que não seja do próprio titular.
   - CPF do titular (depósito): `FRONTEND_CPF_ACTION(user, cpf)`.
   - Notificações (sino): `FRONTEND_NOTIFICATIONS_PROVIDER(user, offset, limit)` e `FRONTEND_NOTIFICATIONS_READ_ACTION(user)`.
   - Extrato consolidado (`/extrato`): `FRONTEND_STATEMENT_SUMMARY_PROVIDER(user)` (totais e contagem por filtro).
   - Histórico de saques (`/withdraw/history`): `FRONTEND_WITHDRAW_HISTORY_PROVIDER(user)`.
   - Fila de saque (cartão no `/withdraw`, consultado a cada 15s em `/acoes/saque/fila`):
     `FRONTEND_WITHDRAW_QUEUE_PROVIDER(user)` → `None` ou `{"position", "amount", "requested_at", "entry_position"?}`.
     **A posição tem que ser calculada na mesma base que registra os pagamentos** (1 + saques não pagos criados
     antes deste) e só cai quando um saque da frente é pago. Nunca um número fixo, estimado ou inflado.
     Sem a setting, o cartão não aparece. Posição inválida esconde o cartão e vai para o log.
   - Check-in: `FRONTEND_CHECKIN_ACTION` pode devolver `amount` → abre o modal "Check-in realizado!".
   - Processo seletivo: `FRONTEND_RECRUIT_ACTION(user, message)`.
   - **Links de suporte e comunidade: Django admin → "Links de atendimento e comunidade"** (registro único,
     model `CommunicationChannels`; rodar `python manage.py migrate`). Suporte = WhatsApp/Telegram do atendimento
     (Chat, fone do cabeçalho, Perfil). Comunidade = grupos/canais (modal de boas-vindas e modal "Entre na comunidade"
     do login/cadastro, que só aparece se houver link). Só aceita https de wa.me / chat.whatsapp.com / whatsapp.com /
     t.me. Cache de 60s por processo. `FRONTEND_WHATSAPP_URL`/`FRONTEND_TELEGRAM_URL`/`FRONTEND_SUPPORT_URL` viram reserva.
   - Modais ao carregar a área logada: "Bem-vindo" e depois o banner "Compartilhe e ganhe"
     (`static/frontend/img/banner-compartilhe-ganhe.jpg` — para mudar a campanha, troque a imagem e o `alt`).
     Aparecem a cada carregamento completo, não na troca de aba.
   - Alterar senha usa o auth do Django direto (`set_password` + mantém a sessão). Não tem limite de tentativas.
   - QR Code: se o provedor devolver `qr_image` (data URI ou https) ela é usada; senão o QR é gerado do copia e cola
     com `qrcode` (dependência opcional, mesma versão do Cointex: `qrcode==8.2`).
   O preview usa valores e ações fictícios de `preview/demo_data.py` (código de bônus de teste: `NEW2026`).
4. Em produção: `python manage.py collectstatic`.

## Trava temporária de login e cadastro

- `FRONTEND_AUTH_LOCKED` (padrão **`True`** — sem a setting, login e cadastro ficam travados). Para liberar:
  `FRONTEND_AUTH_LOCKED = False` no `settings.py`.
- Travado, as telas `/login` e `/reg` abrem normalmente; ao enviar o form, a view recusa **antes** de validar,
  autenticar ou criar usuário (CSRF continua valendo) e aparece o modal "Login/Cadastro temporariamente
  indisponível", com os botões de WhatsApp/Telegram das comunidades (links do admin; sem links, só "Entendi").
  JSON: `503 {"ok": false, "locked": true, "title", "message"}`.
- Textos em `AUTH_LOCK_NOTICES` (`frontend/views.py`).
- **Sessões já abertas continuam logadas** — a trava só impede novos logins/cadastros.

## Login

- Campos: `mobile` e `password`. O celular chega ao backend normalizado (só dígitos, DDD + número, sem +55).
- Autentica via `django.contrib.auth.authenticate(username=<celular>, password=...)`.
  Se o projeto guardar o telefone em outro formato/campo, ajuste **só** `mobile_to_username()` em `frontend/forms.py`
  (ou crie um authentication backend próprio).
- Com JS: o form envia via `fetch` com `Accept: application/json` e a view responde:
  - sucesso → `200 {"ok": true, "redirect": "/..."}` → abre o modal e redireciona
  - erro → `400 {"ok": false, "message": "...", "errors": {"mobile": [...], "password": [...]}}`
- Sem JS: POST normal, redirect no sucesso e erros renderizados no próprio template.
- `?next=` é respeitado só para URLs do mesmo domínio.

## Cadastro (`/reg`)

- Campos: `full_name`, `phone`, `password`, `password_confirmation`, `invitation_code` (opcional).
  Validações e mensagens iguais às do `agrofarm-auth.js` original (celular com exatamente 11 dígitos, senha ≥ 6).
- Cria o usuário com `username` = celular (via `mobile_to_username()`), `first_name` = primeiro nome,
  `last_name` = resto. Os `AUTH_PASSWORD_VALIDATORS` do projeto também são aplicados.
- **Já entra logado** e abre o mesmo modal "Acesso Autorizado!" do login, redirecionando para
  `LOGIN_REDIRECT_URL` (ou `?next=` do mesmo domínio). No original, o cadastro mandava para o `/login`.
- Telefone já cadastrado → erro no campo: "Este telefone já possui cadastro."
  (inclusive em corrida entre dois envios simultâneos: o `IntegrityError` vira esse mesmo erro, não 500).
- Código de convite: chega normalizado (sem espaços, maiúsculo) em `apply_invitation_code(user, code)`
  em `frontend/forms.py`, que hoje não faz nada. Encaixe aí a regra de indicação do projeto; roda na
  mesma transação da criação do usuário. O front preenche o código a partir de `?code=`,
  `?register_code=` ou `?invitationCode=` (guardado no sessionStorage, como no original).
- Mesmo contrato JSON do login (`{"ok": true, "redirect": ...}` / `400 {"ok": false, "errors": {...}}`).

## Área logada (SPA)

Depois do login/cadastro há uma única carga completa (atrás do modal "Acesso Autorizado!"); dali em diante
a navegação entre abas é sem reload.

- `frontend/app/shell.html` é a casca: `<main id="appView">` + botão "Chat" + navbar fixa. Só o `#appView` é trocado.
- Cada aba é uma `AppPageView` (login obrigatório) com seu fragmento em `frontend/app/pages/<aba>.html`.
  - Acesso direto (F5, link colado): devolve a casca inteira com a aba certa ativa.
  - Troca pelo `app.js` (header `X-SPA-Request: 1`): devolve `{"ok", "tab", "title", "html"}` só com o fragmento.
  - Sessão expirada numa troca: `401 {"redirect": "/login?next=..."}` → o JS vai para o login.
  - `Vary: X-SPA-Request` + `no-store`, para cache nenhum servir o fragmento no lugar da página.
- `static/frontend/js/app.js`: intercepta cliques em `a[data-spa-link]`, usa `history.pushState`,
  suporta voltar/avançar com a rolagem restaurada, cancela a troca anterior se o usuário tocar em outra aba,
  e em qualquer falha (rede, timeout de 15s, 5xx) faz a carga completa da URL em vez de deixar tela quebrada.
- Para criar uma tela nova dentro do SPA: `path(...)` com `AppPageView` em `urls.py`, template em `app/pages/`
  e links com `data-spa-link`. `<script>` dentro do fragmento **não** roda; telas com JS escutam o evento:
  ```js
  document.addEventListener('app:page', (e) => { if (e.detail.tab === 'home') { /* ... */ } });
  ```

## Estrutura

```
frontend/
  templates/frontend/
    base.html                 <head>, fontes, blocos
    auth/base_auth.html       layout hero + coluna do form (login e cadastro)
    auth/login.html
    auth/register.html
    auth/_success_modal.html  modal "Acesso Autorizado!" (login e cadastro)
    app/shell.html            casca da área logada (cabeçalho + navbar + Chat)
    app/pages/*.html          fragmento de cada aba (home, team, deposit, purchases, profile)
    placeholder.html          telas ainda não reconstruídas
  static/frontend/
    css/tokens.css            cores, fontes, raios (valores PROVISÓRIO marcados)
    css/auth.css
    css/app.css               cabeçalho + navbar + botão Chat
    css/home.css              aba Início (todo CSS de aba é carregado na casca: a troca SPA só traz HTML)
    img/home-hero.jpg         foto do topo do Início (gerada por IA, parecida com a do site original)
    js/auth.js
    js/app.js                 navegação SPA
    img/                      login-hero.jpg e logo-new-tractors.png (faltando — ver abaixo)
```

## Pendências

- Imagens originais perdidas: `static/frontend/img/login-hero.jpg` (foto do hero) e `logo-new-tractors.png`.
  Sem elas a página usa um fundo em gradiente verde.
- Favicons, manifest e PWA do site original não foram recriados.
- Rate limiting de tentativas de login e de cadastros fica a cargo do projeto (ex.: django-axes / django-ratelimit).

## Preview local

```
python manage.py migrate
python manage.py createsuperuser   # username = celular só com dígitos, ex. 11987654321
python manage.py runserver
python manage.py test frontend
```
A pasta `preview/` e o `manage.py` servem só para isso — não vão para o projeto real.
