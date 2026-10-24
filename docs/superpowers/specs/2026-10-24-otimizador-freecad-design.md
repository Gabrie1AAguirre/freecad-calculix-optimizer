# Otimizador de forma FreeCAD + CalculiX — Design

Data: 2026-10-24
Status: rascunho para aprovação

## 1. Intenção e o porquê

O usuário modela peças no FreeCAD e quer que uma ferramenta **reduza a tensão de Von Mises** delas automaticamente, de forma iterativa, sem depender de uma LLM nem de trabalho manual a cada rodada. A ferramenta deve:

- funcionar com **qualquer peça**, não só a peça em L de exemplo;
- ser um projeto Python comum, publicável no **GitHub**, que qualquer pessoa com FreeCAD instalado consiga rodar;
- ser lançada pelo **terminal do VS Code** e mostrar a otimização **em tempo real dentro da janela do FreeCAD**.

O usuário é novo na bancada FEM do FreeCAD (aprendeu a montar a primeira análise durante esta conversa). A ferramenta precisa ensinar o preparo e dar mensagens claras em português, não presumir conhecimento de FEM/CalculiX.

O nome original da ideia era "integração FreeCAD + PrePoMax". Decidiu-se (recomendação aceita pelo usuário) **usar somente o FreeCAD** (bancada FEM + Gmsh + CalculiX, todos embutidos no FreeCAD 1.1). O PrePoMax fica fora do fluxo; no máximo é citado no README como visualizador opcional dos resultados. Motivo: só o FreeCAD conhece as cotas paramétricas e as condições de contorno ligadas à geometria; o PrePoMax receberia um sólido sem parâmetros.

## 2. Objetivos, não-objetivos, anti-objetivos

**Objetivos**
- Otimização paramétrica de forma: variar cotas escolhidas pelo usuário, dentro de limites, para encontrar **a peça de menor massa cujo Von Mises máximo fique abaixo de um limite** definido pelo usuário. (Objetivo aprovado pelo usuário.)
- Tudo que é específico de uma peça mora **dentro do `.FCStd`**; o código é genérico.
- Ver a peça mudar e o mapa de cores de Von Mises a cada iteração no FreeCAD GUI.
- Modo `--sem-interface` (headless) para rodadas rápidas/longas.
- Comando de verificação que diz em português o que falta no arquivo.
- Tutorial passo a passo em português usando a peça em L como exemplo, e a peça em L já preparada no repositório.

**Não-objetivos**
- Otimização topológica (remover material livremente, tipo BESO/SIMP).
- Seleção de faces "móveis" por clique — o usuário confirmou que indicar cotas por nome é o que ele quer.
- Suporte a PrePoMax, outros solvers, análises não lineares, dinâmicas, térmicas ou com contato. Só estática linear, um corpo sólido, uma análise.
- Suporte a Linux/macOS na v1 (não proibido, só não testado). Alvo: Windows + FreeCAD 1.1.

**Anti-objetivos (falha mesmo que "funcione")**
- Baixar a tensão simplesmente engrossando tudo até o máximo (por isso o objetivo é massa mínima sob restrição de tensão).
- Reportar como melhoria uma queda de tensão que é artefato numérico (singularidade em canto vivo, borda de fixação ou borda de aplicação de força).
- Continuar otimizando quando a fixação/força "pulou" para outra face por causa do problema de nomes topológicos do FreeCAD, gerando resultados sem sentido sem avisar.
- Sobrescrever o arquivo original do usuário.
- Erros crus do CalculiX/Gmsh/FreeCAD jogados na cara do usuário sem explicação.

## 3. Ambiente e restrições (verificado na máquina do usuário)

- Windows 11, FreeCAD **1.1.4** em `C:\Program Files\FreeCAD 1.1\` com `bin\freecad.exe`, `bin\freecadcmd.exe`, `bin\python.exe` (Python 3.11.14), `bin\ccx.exe`, `bin\gmsh.exe`.
- O Python do FreeCAD já tem **numpy 1.26, scipy 1.16, matplotlib 3.10**. Nenhuma dependência extra deve ser instalada.
- O usuário também tem Python 3.11.9 do sistema (é o `python` do VS Code). Ele **não** consegue importar o módulo FreeCAD diretamente.
- Para rodar scripts no `freecadcmd` usar `freecadcmd.exe -c "exec(open(r'<caminho>').read())"` — passar o caminho do script como argumento posicional **não** executou o script nos testes desta conversa.
- O projeto ainda não é um repositório git; virará repositório GitHub.

## 4. Peça de exemplo (estado atual de `L_part.FCStd`)

Inspecionado via freecadcmd:
- `Body` com `Sketch` (perfil em L no plano XZ: perna horizontal 180×30, perna vertical 30×230) → `Pad` 20 mm; `Sketch001` + `Pad001` (10 mm, reverso) só para dividir uma face 20×20 no topo interno da perna vertical (volume total não muda: 228 000 mm³).
- `Analysis` com `ConstraintFixed` (Face2, base da perna horizontal), `ConstraintForce` (Face12, 5000 N na direção −X), `MaterialSolid` (Steel-C10: E 210 GPa, ν 0,3, escoamento 380 MPa, ruptura 650 MPa), `FEMMeshGmsh` (tam. máx. 5 mm, 2ª ordem), `SolverCcxTools` (estático linear), resultados existentes.
- Resultado atual: Von Mises máx. ≈ 509 MPa no canto interno vivo (30, −10, 31,9); deslocamento máx. 1,66 mm. Tensão de flexão nominal estimada à mão ≈ 317 MPa.
- O canto interno é vivo: o pico é singular e depende da malha. A peça ainda **não** tem planilha nem raio no canto.

## 5. Como uma peça é preparada (convenção — decidida com o usuário)

O usuário prepara cada peça uma vez, no FreeCAD GUI:

1. **Análise FEM** normal na bancada FEM: material, uma ou mais `ConstraintFixed`, uma ou mais `ConstraintForce` (e opcionalmente pressão), malha Gmsh, solver CalculiX. A ferramenta descobre tudo isso sozinha a partir do objeto `Fem::FemAnalysis` do documento.
2. **Planilha chamada `Parametros`** (Label ou Name) contendo **somente o que pode mudar**. Tudo que não está na planilha é fixo. (Ponto levantado e decidido pelo usuário.)
   - Uma linha por parâmetro: coluna A = descrição livre, coluna B = valor com **alias** (o nome que o código usa, ex. `raio_canto`), coluna C = mínimo, coluna D = máximo.
   - As cotas do sketch / propriedades de features são ligadas por expressão (`Parametros.raio_canto`) usando o botão f(x).
3. **Configurações do objetivo**, também na planilha `Parametros`, em células com alias reservado. Mínimo obrigatório: `tensao_limite` (MPa). Opcionais com padrão: `max_iteracoes`. O builder pode adicionar outras opcionais se precisar (ex.: zona de exclusão, ver §7), sempre com padrão sensato.
4. **Raio de canto pelo Sketcher** (fillet de sketch com restrição de raio), não pelo Fillet do PartDesign em aresta, para não depender de nome de aresta. Isso vira recomendação no tutorial e aviso no `--checar` quando houver `PartDesign::Fillet` ligado a um parâmetro.

O layout exato das células de configuração (linhas separadas abaixo dos parâmetros, ou outra área) fica a critério do builder, desde que seja documentado no tutorial e o código identifique parâmetros vs. configurações sem ambiguidade (ex.: aliases reservados).

## 6. Experiência de uso

```
python otimizar.py exemplos/L_part.FCStd            # abre o FreeCAD e otimiza ao vivo
python otimizar.py exemplos/L_part.FCStd --sem-interface
python otimizar.py exemplos/L_part.FCStd --checar   # só verifica a preparação
```

- `otimizar.py` roda com o **Python do sistema, só biblioteca padrão**: localiza o FreeCAD (padrão `C:\Program Files\FreeCAD 1.1\bin`, sobrescrevível por `--freecad <pasta>` e variável de ambiente), e lança `freecad.exe` (modo ao vivo) ou `freecadcmd.exe` (headless/checar) com o script interno. A lógica de otimização fica num pacote que roda dentro do Python do FreeCAD.
- **Antes do loop**, roda uma análise com os valores atuais e mostra Von Mises máximo, onde ele está e a massa — "linha de base".
- **A cada iteração**, no modo ao vivo: geometria recalculada na tela, peça pintada com Von Mises (mesma escala de cores da bancada FEM), linha na Report View e no terminal do VS Code:

```
iter  raio_canto  esp_vertical  VonMises_max  massa    status
  1      1.0         30.0         509 MPa    1.79 kg   acima do limite
  3     14.0         35.0         247 MPa    1.95 kg   OK ✓ melhor até agora
```

- O terminal do VS Code precisa receber essas linhas em tempo real também no modo ao vivo (o FreeCAD GUI é outro processo; o builder escolhe como: stdout, arquivo de log seguido pelo lançador, etc.).
- Aceitável que a janela pareça travada enquanto o CalculiX resolve; desejável evitar.
- **No final**: melhor versão aberta no FreeCAD (modo ao vivo), resumo no terminal (melhor ponto, se atingiu o limite, massa vs. original, tensão vs. original).
- Se nenhuma combinação nos limites atinge `tensao_limite`: avisa claramente e entrega o melhor viável-mais-próximo (menor tensão), não falha calado.

## 7. Comportamento da otimização (decisões do builder já tomadas por mim — marcadas)

- **Formulação**: minimizar massa (volume × densidade do material) sujeito a `VonMises_max ≤ tensao_limite`, com cada parâmetro dentro de [mín, máx]. *(minha decisão)*
- **Algoritmo**: sem derivadas, com restrição, poucas avaliações (cada avaliação = recompute + malha + solve, segundos a ~1 min). Sugestão: COBYLA do scipy partindo dos valores atuais, ou equivalente. Escolha final do builder. A avaliação da FEA é ruidosa (malha muda), o algoritmo deve tolerar isso. *(minha decisão: scipy disponível, nada a instalar)*
- **Medida de tensão**: Von Mises máximo nodal, **excluindo nós próximos às faces das condições de contorno** (fixação e força), porque bordas de fixação/aplicação de carga são singularidades artificiais que dominariam o máximo depois que o canto for arredondado. Distância de exclusão com padrão sensato (ex.: ~2× tamanho de elemento) e configurável na planilha. O máximo bruto (sem exclusão) também é registrado no CSV para transparência. *(minha decisão)*
- **A exclusão nunca pode esconder um pico real em silêncio.** Risco: numa peça real o ponto crítico pode estar colado numa face de fixação (raiz de suporte parafusado), ou no exemplo a perna fina pode levar o canto para dentro da zona; o otimizador então afinaria a peça e diria "OK ✓" sobre algo acima do limite. Regras *(minha decisão, apresentada ao usuário para veto)*:
  - Padrão: excluir zona em volta de forças/pressões **e** de fixações.
  - Toda iteração compara o máximo **dentro** das zonas excluídas com `tensao_limite`. Se o máximo bruto dentro da zona passar do limite, a iteração ganha status **"OK ⚠ verificar"** (não "OK ✓"), com o local do pico; o resumo final e o CSV destacam isso, e o melhor ponto é escolhido preferindo iterações "OK ✓" limpas.
  - Também sinalizar quando o máximo filtrado está na borda da zona (indício de que o gradiente continua para dentro dela).
  - O usuário pode desligar a exclusão por condição de contorno (ex.: um alias/opção por fixação ou força na planilha; formato a critério do builder) e mudar a distância.
  - O tutorial explica em linguagem simples por que essas zonas existem e quando desligar.
- **Malha**: usa as configurações de malha do próprio usuário (`FEMMeshGmsh`) em todas as iterações; a ferramenta não refina malha por conta própria na v1. O tutorial explica que canto vivo não tem tensão "verdadeira". *(minha decisão)*
- **Proteção contra nomes topológicos**: depois de cada recompute, verificar que cada condição de contorno ainda aponta para uma face existente e "parecida" com a original (ex.: normal e posição/área do centroide dentro de tolerância). Se não, a iteração é marcada inválida com mensagem clara; se acontecer na linha de base ou repetidamente, parar e explicar. *(minha decisão)*
- **Falhas de avaliação** (recompute com erro, sketch impossível, Gmsh ou CalculiX falham): iteração marcada como inválida no CSV com motivo, tratada pelo otimizador como ponto ruim; a rodada continua. *(minha decisão)*
- **Parada**: convergência do algoritmo ou `max_iteracoes` (padrão 30). Ctrl+C no terminal (ou fechar o FreeCAD) encerra salvando o melhor até então. *(minha decisão)*
- **Arquivo original nunca é modificado**; trabalha numa cópia.

## 8. Saídas

Por rodada, numa pasta `resultados/<nome_da_peca>_<data-hora>/`:
- `<peca>_otimizada.FCStd` — melhor ponto viável (ou melhor encontrado, se nenhum viável), com resultados FEM dentro;
- `historico.csv` — uma linha por iteração: valores dos parâmetros, Von Mises (filtrado e bruto), local do máximo, massa, status/motivo;
- `grafico.png` — tensão e massa por iteração, linha do limite (matplotlib);
- `log.txt` — saída completa.
*(estrutura de pastas: minha decisão)*

## 9. Verificação (`--checar`)

Mensagens em português, uma por problema, dizendo como corrigir. Mínimo:
- não há `Analysis`, material, fixação, força, malha ou solver;
- não há planilha `Parametros`, ou ela não tem nenhum parâmetro;
- parâmetro sem mínimo/máximo, mínimo ≥ máximo, valor atual fora dos limites;
- parâmetro que não é usado por nenhuma expressão no documento (ligação esquecida);
- falta `tensao_limite`;
- parâmetro ligado a `PartDesign::Fillet`/`Chamfer` (aviso, não erro);
- o documento não recomputa sem erro com os valores atuais.

## 10. Repositório e documentação

- Estrutura e nomes de módulos: a critério do builder. Código, mensagens e README em **português** (o usuário é brasileiro; aliases da planilha também são em português). *(minha decisão)*
- `exemplos/L_part.FCStd`: a peça em L **preparada** (planilha `Parametros`, raio de canto via sketch fillet ligado a `raio_canto`, espessuras das pernas ligadas a parâmetros, `tensao_limite` p.ex. 250 MPa ≈ 380/1,5). A preparação pode ser feita por script, mas o resultado deve abrir e funcionar normalmente no FreeCAD GUI. O `L_part.FCStd` original do usuário na raiz deve ser preservado.
- `README.md`: o que é, requisitos (Windows, FreeCAD 1.1), como rodar o exemplo, e **tutorial passo a passo** de preparo de uma peça nova (análise FEM, planilha, aliases, f(x), sketch fillet, `--checar`). Prints de tela são desejáveis; se não for possível gerá-los automaticamente, deixar marcadores claros para o usuário completar.
- Licença MIT. *(minha decisão)*
- Testes: pelo menos um teste de ponta a ponta que roda o exemplo headless com poucas iterações e confere que a tensão final é menor que a inicial e que o resultado respeita os limites; mais testes unitários onde fizer sentido.

## 11. Deixado ao builder

- Arquitetura interna, nomes de módulos, como o processo GUI comunica progresso ao terminal.
- Algoritmo exato de otimização e tolerâncias.
- Como pintar Von Mises na GUI (pipeline de pós-processamento da FEM ou cor por nó na malha).
- Layout exato da área de configurações da planilha.
- Como evitar travamento da GUI durante o solve.
