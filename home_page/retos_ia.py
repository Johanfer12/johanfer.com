"""Datos de Retos → Inteligencia artificial (/retos/?tema=ia).

Todo leído el 23/11/2026 de las fuentes que se citan en cada bloque, sin
estimar nada a mano; lo que es suma de cifras oficiales va marcado como
derivado. Al actualizar, reemplazar el bloque entero.

Las cifras de los textos las calcula `contexto()` a partir de las series.
"""

from .retos import MESES, _coma

# ---------------------------------------------------------------------------
# 1. CÓMPUTO DE ENTRENAMIENTO DE MODELOS NOTABLES (FLOP)
# Fuente: Epoch AI, "Notable AI models", CSV https://epoch.ai/data/notable_ai_models.csv
#   (página: https://epoch.ai/data/ai-models ; CSV "Updated Nov. 17, 2026"). Leído 23/11/2026.
# Selección: todos los modelos desde 2010 con cómputo conocido y marca
#   "Frontier model" = True (72; Epoch define frontera = top-5 por cómputo de
#   entrenamiento en el momento de su lanzamiento), más 30 hitos notables sin esa
#   marca (Transformer, BERT, GPT-2, GPT-5, DeepSeek-V3/R1, Kimi, Qwen...) -> 102 puntos.
#   `frontera` indica cuál es cuál. Último punto: GPT-6 Astra (2026-09-03, 9,4e26 FLOP).
# Salvedades: muchas cifras son estimaciones de Epoch (columna `confianza`:
#   Confident / Likely / Speculative). Modelos recientes cerrados (p. ej. Gemini 4
#   Carbon, 2026-11-10) no tienen cómputo publicado y no aparecen.
# Tasa citada por Epoch (https://epoch.ai/trends, leído 23/11/2026): "Training compute
#   for frontier language models has been growing at 5x per year since 2020" =
#   duplicación cada 5,2 meses (IC 90 %: 4x-6x/año; 4,6-6,0 meses).
COMPUTO_TASA_EPOCH = {
    'multiplicador_anual': 5, 'ic90_multiplicador': (4, 6),
    'duplicacion_meses': 5.2, 'ic90_duplicacion_meses': (4.6, 6.0),
    'desde': 2020, 'ambito': 'modelos de lenguaje de frontera',
    'fuente': 'https://epoch.ai/trends',
}
COMPUTO_ENTRENAMIENTO = [
    {'modelo': 'RNN LM', 'organizacion': 'Johns Hopkins University', 'fecha': '2010-09-26', 'flop': 5.396e+16, 'frontera': True, 'confianza': 'Speculative'},
    {'modelo': 'Deep Autoencoders', 'organizacion': 'University of Toronto', 'fecha': '2011-04-29', 'flop': 3.673e+16, 'frontera': True, 'confianza': 'Confident'},
    {'modelo': 'CNN Committee (MNIST)', 'organizacion': 'IDSIA', 'fecha': '2011-09-18', 'flop': 5.2e+16, 'frontera': True, 'confianza': 'Likely'},
    {'modelo': 'Dropout (ImageNet)', 'organizacion': 'University of Toronto', 'fecha': '2012-06-03', 'flop': 2.732e+17, 'frontera': True, 'confianza': 'Confident'},
    {'modelo': 'Unsupervised High-level Feature Learner', 'organizacion': 'Google', 'fecha': '2012-07-12', 'flop': 6e+17, 'frontera': True, 'confianza': 'Likely'},
    {'modelo': 'AlexNet', 'organizacion': 'University of Toronto', 'fecha': '2012-09-30', 'flop': 4.7e+17, 'frontera': True, 'confianza': 'Confident'},
    {'modelo': 'DNN EM segmentation', 'organizacion': 'IDSIA,SUPSI', 'fecha': '2012-12-03', 'flop': 4.78e+17, 'frontera': True, 'confianza': 'Confident'},
    {'modelo': 'DistBelief NNLM', 'organizacion': 'Google', 'fecha': '2013-01-16', 'flop': 2.613e+18, 'frontera': True, 'confianza': 'Likely'},
    {'modelo': 'Word2Vec (large)', 'organizacion': 'Google', 'fecha': '2013-10-16', 'flop': 3.888e+16, 'frontera': False, 'confianza': 'Likely'},
    {'modelo': 'Visualizing CNNs', 'organizacion': 'New York University (NYU)', 'fecha': '2013-11-12', 'flop': 5.32e+17, 'frontera': True, 'confianza': 'Confident'},
    {'modelo': 'TransE', 'organizacion': 'Universite de Technologie de Compiègne – CNRS,Google', 'fecha': '2013-12-05', 'flop': 1.341e+18, 'frontera': True, 'confianza': 'Speculative'},
    {'modelo': 'SPPNet', 'organizacion': 'Microsoft,Xi’an Jiaotong University,University of Science and Technology of China (USTC)', 'fecha': '2014-06-18', 'flop': 3.411e+18, 'frontera': True, 'confianza': 'Confident'},
    {'modelo': 'RNNsearch-50*', 'organizacion': 'Jacobs University Bremen,University of Montreal / Université de Montréal', 'fecha': '2014-09-01', 'flop': 1.555e+18, 'frontera': True, 'confianza': 'Confident'},
    {'modelo': 'VGG16', 'organizacion': 'University of Oxford', 'fecha': '2014-09-04', 'flop': 1.229e+19, 'frontera': True, 'confianza': 'Confident'},
    {'modelo': 'VGG19', 'organizacion': 'University of Oxford', 'fecha': '2014-09-04', 'flop': 1.1e+19, 'frontera': True, 'confianza': 'Likely'},
    {'modelo': 'Seq2Seq LSTM', 'organizacion': 'Google', 'fecha': '2014-09-10', 'flop': 5.6e+19, 'frontera': True, 'confianza': 'Confident'},
    {'modelo': 'SNM-skip', 'organizacion': 'Google', 'fecha': '2014-12-03', 'flop': 2.976e+20, 'frontera': True, 'confianza': 'Speculative'},
    {'modelo': 'MSRA (C, PReLU)', 'organizacion': 'Microsoft Research', 'fecha': '2015-02-06', 'flop': 2.397e+19, 'frontera': True, 'confianza': 'Confident'},
    {'modelo': 'AlphaGo Fan', 'organizacion': 'DeepMind', 'fecha': '2015-10-01', 'flop': 3.8e+20, 'frontera': True, 'confianza': 'Likely'},
    {'modelo': 'SAF R-CNN', 'organizacion': 'Beijing Institute of Technology,Sun Yat-sen University,Panasonic R&D,National University of Singapore', 'fecha': '2015-10-28', 'flop': 1.231e+19, 'frontera': True, 'confianza': 'Likely'},
    {'modelo': 'Inception v3', 'organizacion': 'Google,University College London (UCL)', 'fecha': '2015-12-02', 'flop': 1e+20, 'frontera': True, 'confianza': 'Likely'},
    {'modelo': 'ResNet-152 (ImageNet)', 'organizacion': 'Microsoft', 'fecha': '2015-12-10', 'flop': 1.041e+19, 'frontera': False, 'confianza': 'Confident'},
    {'modelo': 'AlphaGo Lee', 'organizacion': 'DeepMind', 'fecha': '2016-01-27', 'flop': 1.9e+21, 'frontera': True, 'confianza': 'Speculative'},
    {'modelo': 'GNMT', 'organizacion': 'Google', 'fecha': '2016-09-26', 'flop': 6.62e+21, 'frontera': True, 'confianza': 'Likely'},
    {'modelo': 'Xception', 'organizacion': 'Google', 'fecha': '2016-10-07', 'flop': 4.36e+20, 'frontera': True, 'confianza': 'Confident'},
    {'modelo': 'NASv3 (CIFAR-10)', 'organizacion': 'Google Brain', 'fecha': '2016-11-05', 'flop': 2.2e+21, 'frontera': True, 'confianza': 'Likely'},
    {'modelo': 'Transformer', 'organizacion': 'Google Research,Google Brain', 'fecha': '2017-06-12', 'flop': 7.425e+18, 'frontera': False, 'confianza': 'Confident'},
    {'modelo': 'JFT', 'organizacion': 'Google Research,Carnegie Mellon University (CMU)', 'fecha': '2017-07-10', 'flop': 8.43e+20, 'frontera': True, 'confianza': 'Confident'},
    {'modelo': 'OpenAI TI7 DOTA 1v1', 'organizacion': 'OpenAI', 'fecha': '2017-08-11', 'flop': 6.046e+20, 'frontera': True, 'confianza': 'Confident'},
    {'modelo': 'AlphaGo Zero', 'organizacion': 'DeepMind', 'fecha': '2017-10-18', 'flop': 6.494e+20, 'frontera': True, 'confianza': 'Confident'},
    {'modelo': 'ResNeXt-101 32x48d', 'organizacion': 'Facebook', 'fecha': '2018-05-02', 'flop': 8.744e+21, 'frontera': True, 'confianza': 'Confident'},
    {'modelo': 'GPT-1', 'organizacion': 'OpenAI', 'fecha': '2018-06-01', 'flop': 1.758e+19, 'frontera': False, 'confianza': 'Likely'},
    {'modelo': 'BERT-Large', 'organizacion': 'Google', 'fecha': '2018-10-11', 'flop': 2.85e+20, 'frontera': False, 'confianza': 'Confident'},
    {'modelo': 'GPT-2 (1.5B)', 'organizacion': 'OpenAI', 'fecha': '2019-02-14', 'flop': 1.92e+21, 'frontera': False, 'confianza': 'Speculative'},
    {'modelo': 'XLNet', 'organizacion': 'Carnegie Mellon University (CMU),Google Brain', 'fecha': '2019-06-01', 'flop': 6.19e+21, 'frontera': True, 'confianza': 'Confident'},
    {'modelo': 'RoBERTa Large', 'organizacion': 'Facebook,University of Washington', 'fecha': '2019-07-01', 'flop': 8.507e+21, 'frontera': True, 'confianza': 'Confident'},
    {'modelo': 'Megatron-BERT', 'organizacion': 'Nvidia', 'fecha': '2019-09-17', 'flop': 2.2e+22, 'frontera': True, 'confianza': 'Confident'},
    {'modelo': 'Megatron-LM (8.3B)', 'organizacion': 'Nvidia', 'fecha': '2019-09-17', 'flop': 9.1e+21, 'frontera': True, 'confianza': 'Likely'},
    {'modelo': 'T5-11B', 'organizacion': 'Google', 'fecha': '2019-10-23', 'flop': 3.3e+22, 'frontera': True, 'confianza': 'Confident'},
    {'modelo': 'T5-3B', 'organizacion': 'Google', 'fecha': '2019-10-23', 'flop': 9e+21, 'frontera': True, 'confianza': 'Confident'},
    {'modelo': 'AlphaStar', 'organizacion': 'DeepMind', 'fecha': '2019-10-30', 'flop': 1.077e+23, 'frontera': True, 'confianza': 'Confident'},
    {'modelo': 'XLM-RoBERTa', 'organizacion': 'Facebook AI', 'fecha': '2019-11-05', 'flop': 2.076e+22, 'frontera': True, 'confianza': 'Confident'},
    {'modelo': 'Noisy Student (L2)', 'organizacion': 'Carnegie Mellon University (CMU),Google', 'fecha': '2019-11-11', 'flop': 2.612e+22, 'frontera': True, 'confianza': 'Confident'},
    {'modelo': 'OpenAI Five', 'organizacion': 'OpenAI', 'fecha': '2019-12-13', 'flop': 6.7e+22, 'frontera': True, 'confianza': 'Confident'},
    {'modelo': 'Meena', 'organizacion': 'Google Brain', 'fecha': '2020-01-28', 'flop': 1.12e+23, 'frontera': True, 'confianza': 'Confident'},
    {'modelo': 'GPT-3 175B (davinci)', 'organizacion': 'OpenAI', 'fecha': '2020-05-28', 'flop': 3.14e+23, 'frontera': True, 'confianza': 'Confident'},
    {'modelo': 'GShard (dense)', 'organizacion': 'Google', 'fecha': '2020-06-30', 'flop': 4.765e+22, 'frontera': True, 'confianza': 'Confident'},
    {'modelo': 'mT5-XXL', 'organizacion': 'Google,Google Research', 'fecha': '2020-10-20', 'flop': 8.2e+22, 'frontera': True, 'confianza': 'Confident'},
    {'modelo': 'AlphaFold 2', 'organizacion': 'DeepMind', 'fecha': '2020-11-30', 'flop': 2.99e+21, 'frontera': False, 'confianza': 'Likely'},
    {'modelo': 'DALL-E', 'organizacion': 'OpenAI', 'fecha': '2021-01-05', 'flop': 4.7e+22, 'frontera': False, 'confianza': 'Likely'},
    {'modelo': 'Switch', 'organizacion': 'Google', 'fecha': '2021-01-11', 'flop': 8.22e+22, 'frontera': True, 'confianza': 'Confident'},
    {'modelo': 'Jurassic-1-Jumbo', 'organizacion': 'AI21 Labs', 'fecha': '2021-08-11', 'flop': 3.7e+23, 'frontera': True, 'confianza': 'Confident'},
    {'modelo': 'FLAN 137B', 'organizacion': 'Google Research', 'fecha': '2021-09-03', 'flop': 2.047e+24, 'frontera': True, 'confianza': 'Confident'},
    {'modelo': 'HyperCLOVA 204B', 'organizacion': 'NAVER', 'fecha': '2021-09-10', 'flop': 2e+23, 'frontera': True, 'confianza': 'Speculative'},
    {'modelo': 'Megatron-Turing NLG 530B', 'organizacion': 'Microsoft,Nvidia', 'fecha': '2021-10-11', 'flop': 8.586e+23, 'frontera': True, 'confianza': 'Confident'},
    {'modelo': 'Yuan 1.0', 'organizacion': 'Inspur', 'fecha': '2021-10-12', 'flop': 3.538e+23, 'frontera': True, 'confianza': 'Confident'},
    {'modelo': 'Gopher (280B)', 'organizacion': 'DeepMind', 'fecha': '2021-12-08', 'flop': 6.31e+23, 'frontera': True, 'confianza': 'Confident'},
    {'modelo': 'ERNIE 3.0 Titan', 'organizacion': 'Baidu,Peng Cheng Laboratory', 'fecha': '2021-12-23', 'flop': 1.042e+24, 'frontera': True, 'confianza': 'Confident'},
    {'modelo': 'GPT-3.5 (davinci-002)', 'organizacion': 'OpenAI', 'fecha': '2022-03-15', 'flop': 2.578e+24, 'frontera': True, 'confianza': 'Speculative'},
    {'modelo': 'Chinchilla', 'organizacion': 'DeepMind', 'fecha': '2022-03-29', 'flop': 5.76e+23, 'frontera': False, 'confianza': 'Confident'},
    {'modelo': 'PaLM (540B)', 'organizacion': 'Google Research', 'fecha': '2022-04-04', 'flop': 2.527e+24, 'frontera': True, 'confianza': 'Confident'},
    {'modelo': 'Stable Diffusion (LDM-KL-8-G)', 'organizacion': 'Runway,Ludwig Maximilian University of Munich,Heidelberg University', 'fecha': '2022-04-13', 'flop': 5e+22, 'frontera': False, 'confianza': 'Confident'},
    {'modelo': 'Minerva (540B)', 'organizacion': 'Google', 'fecha': '2022-06-29', 'flop': 2.742e+24, 'frontera': True, 'confianza': 'Confident'},
    {'modelo': 'Flan-PaLM 540B', 'organizacion': 'Google', 'fecha': '2022-10-20', 'flop': 2.54e+24, 'frontera': True, 'confianza': 'Confident'},
    {'modelo': 'U-PaLM (540B)', 'organizacion': 'Google', 'fecha': '2022-10-20', 'flop': 2.53e+24, 'frontera': True, 'confianza': 'Confident'},
    {'modelo': 'LLaMA-65B', 'organizacion': 'Meta AI', 'fecha': '2023-02-24', 'flop': 5.5e+23, 'frontera': False, 'confianza': 'Confident'},
    {'modelo': 'GPT-4 (Mar 2023)', 'organizacion': 'OpenAI', 'fecha': '2023-03-15', 'flop': 2.1e+25, 'frontera': True, 'confianza': 'Likely'},
    {'modelo': 'PaLM 2', 'organizacion': 'Google', 'fecha': '2023-05-10', 'flop': 7.34e+24, 'frontera': True, 'confianza': 'Likely'},
    {'modelo': 'GPT-4 (Jun 2023)', 'organizacion': 'OpenAI', 'fecha': '2023-06-13', 'flop': 2.1e+25, 'frontera': True, 'confianza': 'Likely'},
    {'modelo': 'Claude 2', 'organizacion': 'Anthropic', 'fecha': '2023-07-11', 'flop': 3.866e+24, 'frontera': True, 'confianza': 'Speculative'},
    {'modelo': 'Llama 2-70B', 'organizacion': 'Meta AI', 'fecha': '2023-07-18', 'flop': 8.1e+23, 'frontera': False, 'confianza': 'Confident'},
    {'modelo': 'Falcon-180B', 'organizacion': 'Technology Innovation Institute', 'fecha': '2023-09-06', 'flop': 3.76e+24, 'frontera': True, 'confianza': 'Confident'},
    {'modelo': 'Amazon Titan', 'organizacion': 'Amazon', 'fecha': '2023-09-28', 'flop': 4.8e+24, 'frontera': True, 'confianza': 'Likely'},
    {'modelo': 'Grok-1', 'organizacion': 'xAI', 'fecha': '2023-11-04', 'flop': 2.9e+24, 'frontera': False, 'confianza': 'Likely'},
    {'modelo': 'Inflection-2', 'organizacion': 'Inflection AI', 'fecha': '2023-11-22', 'flop': 1.001e+25, 'frontera': True, 'confianza': 'Confident'},
    {'modelo': 'Gemini 1.0 Ultra', 'organizacion': 'Google DeepMind', 'fecha': '2023-12-06', 'flop': 5e+25, 'frontera': True, 'confianza': 'Speculative'},
    {'modelo': 'Llama 3-70B', 'organizacion': 'Meta AI', 'fecha': '2024-04-18', 'flop': 7.861e+24, 'frontera': False, 'confianza': 'Confident'},
    {'modelo': 'Nemotron-4 340B', 'organizacion': 'Nvidia', 'fecha': '2024-06-14', 'flop': 1.8e+25, 'frontera': True, 'confianza': 'Confident'},
    {'modelo': 'Claude 3.5 Sonnet', 'organizacion': 'Anthropic', 'fecha': '2024-06-20', 'flop': 2.7e+25, 'frontera': True, 'confianza': 'Speculative'},
    {'modelo': 'Llama 3.1-405B', 'organizacion': 'Meta AI', 'fecha': '2024-07-23', 'flop': 3.8e+25, 'frontera': True, 'confianza': 'Confident'},
    {'modelo': 'Grok-2', 'organizacion': 'xAI', 'fecha': '2024-08-13', 'flop': 2.96e+25, 'frontera': True, 'confianza': 'Confident'},
    {'modelo': 'Qwen2.5-72B', 'organizacion': 'Alibaba', 'fecha': '2024-09-19', 'flop': 7.8e+24, 'frontera': False, 'confianza': 'Confident'},
    {'modelo': 'Doubao-pro', 'organizacion': 'ByteDance', 'fecha': '2024-10-28', 'flop': 2.505e+25, 'frontera': False, 'confianza': 'Likely'},
    {'modelo': 'DeepSeek-V3', 'organizacion': 'DeepSeek', 'fecha': '2024-12-24', 'flop': 3.3e+24, 'frontera': False, 'confianza': 'Confident'},
    {'modelo': 'DeepSeek-R1', 'organizacion': 'DeepSeek', 'fecha': '2025-01-20', 'flop': 3.3e+24, 'frontera': False, 'confianza': 'Confident'},
    {'modelo': 'Grok 3', 'organizacion': 'xAI', 'fecha': '2025-02-17', 'flop': 3.5e+26, 'frontera': True, 'confianza': 'Likely'},
    {'modelo': 'Claude 3.7 Sonnet', 'organizacion': 'Anthropic', 'fecha': '2025-02-24', 'flop': 3.35e+25, 'frontera': False, 'confianza': 'Likely'},
    {'modelo': 'GPT-4.5', 'organizacion': 'OpenAI', 'fecha': '2025-02-27', 'flop': 3.8e+26, 'frontera': True, 'confianza': 'Likely'},
    {'modelo': 'Llama 4 Behemoth (preview)', 'organizacion': 'Meta AI', 'fecha': '2025-04-05', 'flop': 5.184e+25, 'frontera': True, 'confianza': 'Likely'},
    {'modelo': 'Qwen3-235B-A22B', 'organizacion': 'Alibaba', 'fecha': '2025-04-29', 'flop': 4.752e+24, 'frontera': False, 'confianza': 'Likely'},
    {'modelo': 'Grok 4', 'organizacion': 'xAI', 'fecha': '2025-07-09', 'flop': 5e+26, 'frontera': True, 'confianza': 'Speculative'},
    {'modelo': 'Kimi K2', 'organizacion': 'Moonshot', 'fecha': '2025-07-11', 'flop': 2.976e+24, 'frontera': False, 'confianza': 'Confident'},
    {'modelo': 'GPT-5', 'organizacion': 'OpenAI', 'fecha': '2025-08-07', 'flop': 6.6e+25, 'frontera': False, 'confianza': 'Speculative'},
    {'modelo': 'Qwen3-Max', 'organizacion': 'Alibaba', 'fecha': '2025-09-05', 'flop': 1.512e+25, 'frontera': False, 'confianza': 'Speculative'},
    {'modelo': 'Kimi K2.5', 'organizacion': 'Moonshot', 'fecha': '2026-02-02', 'flop': 5.8e+24, 'frontera': False, 'confianza': 'Likely'},
    {'modelo': 'Composer 2', 'organizacion': 'Cursor', 'fecha': '2026-03-19', 'flop': 2.32e+25, 'frontera': False, 'confianza': 'Confident'},
    {'modelo': 'DeepSeek-V4-Pro', 'organizacion': 'DeepSeek', 'fecha': '2026-04-24', 'flop': 9.702e+24, 'frontera': False, 'confianza': 'Likely'},
    {'modelo': 'Composer 2.5', 'organizacion': 'Cursor', 'fecha': '2026-05-18', 'flop': 3.87e+25, 'frontera': False, 'confianza': 'Likely'},
    {'modelo': 'Kimi K3', 'organizacion': 'Moonshot', 'fecha': '2026-07-16', 'flop': 2e+25, 'frontera': False, 'confianza': 'Speculative'},
    {'modelo': 'GPT-6 Astra', 'organizacion': 'OpenAI', 'fecha': '2026-09-03', 'flop': 9.4e+26, 'frontera': True, 'confianza': 'Likely'},
    {'modelo': 'Mistral Large 4', 'organizacion': 'Mistral AI', 'fecha': '2026-10-06', 'flop': 1.24e+25, 'frontera': False, 'confianza': 'Confident'},
    {'modelo': 'MAI-Base-2', 'organizacion': 'Microsoft', 'fecha': '2026-10-15', 'flop': 2.4e+25, 'frontera': False, 'confianza': 'Confident'},
]

# ---------------------------------------------------------------------------
# 2. HORIZONTE TEMPORAL DE AGENTES (METR), 50 % de éxito
# Fuente: METR, "Task-Completion Time Horizons of Frontier AI Models",
#   https://metr.org/time-horizons/ (LAST UPDATED September 8, 2026) y su fichero
#   bruto https://metr.org/assets/benchmark_results_1_1.yaml (METR-Horizon-v1.1). Leído 23/11/2026.
# Cobertura: los 26 modelos del fichero, de GPT-2 (2019-02-14) a Claude Mythos Preview
#   temprana (lanzamiento 2026-04-07; añadido a la página el 08/05/2026).
#   p50_min = duración (minutos de experto humano) de las tareas que el modelo
#   completa con 50 % de éxito; ic95_* = intervalo de confianza del fichero; p80_min =
#   lo mismo al 80 %. `sota` = marca is_sota de METR. Fecha = lanzamiento del modelo.
# Salvedades: METR declara que la página "is no longer actively updated" (08/09/2026):
#   no hay mediciones de modelos posteriores. La propia página advierte que las medidas
#   por encima de 16 h (960 min) "are unreliable with our current task suite": Mythos
#   (1044,8 min, IC 508,9-3304,3) y el IC de Opus 4.6 son muy inciertos. Las tareas son
#   de software/IA, bien especificadas y puntuables automáticamente.
# Tiempo de duplicación (del mismo YAML, que excluye los puntos con p50 > 16 h):
HORIZONTE_DUPLICACION = {
    'desde_2023_dias': 128.7, 'desde_2023_ic_dias': (104.4, 158.0),   # ~4,2 meses
    'historico_dias': 187.8,                                          # 2019-2026, ~6,2 meses
    'fuente': 'https://metr.org/assets/benchmark_results_1_1.yaml',
}
HORIZONTE_METR = [
    {'modelo': 'GPT-2', 'id_metr': 'gpt2', 'fecha': '2019-02-14', 'p50_min': 0.1, 'ic95_bajo': 0.0, 'ic95_alto': 0.1, 'p80_min': 0.0, 'sota': True},
    {'modelo': 'GPT-3 (davinci-002)', 'id_metr': 'davinci_002', 'fecha': '2020-05-28', 'p50_min': 0.1, 'ic95_bajo': 0.1, 'ic95_alto': 0.2, 'p80_min': 0.1, 'sota': True},
    {'modelo': 'GPT-3.5 Turbo Instruct', 'id_metr': 'gpt_3_5_turbo_instruct', 'fecha': '2022-03-15', 'p50_min': 0.6, 'ic95_bajo': 0.3, 'ic95_alto': 1.1, 'p80_min': 0.3, 'sota': True},
    {'modelo': 'GPT-4', 'id_metr': 'gpt_4', 'fecha': '2023-03-14', 'p50_min': 4.0, 'ic95_bajo': 1.9, 'ic95_alto': 8.0, 'p80_min': 0.9, 'sota': True},
    {'modelo': 'GPT-4 (1106)', 'id_metr': 'gpt_4_1106_inspect', 'fecha': '2023-11-06', 'p50_min': 4.0, 'ic95_bajo': 1.9, 'ic95_alto': 8.4, 'p80_min': 0.8, 'sota': True},
    {'modelo': 'Claude 3 Opus', 'id_metr': 'claude_3_opus_inspect', 'fecha': '2024-03-04', 'p50_min': 4.0, 'ic95_bajo': 1.7, 'ic95_alto': 8.8, 'p80_min': 0.6, 'sota': False},
    {'modelo': 'GPT-4 Turbo', 'id_metr': 'gpt_4_turbo_inspect', 'fecha': '2024-04-09', 'p50_min': 3.7, 'ic95_bajo': 2.0, 'ic95_alto': 6.7, 'p80_min': 0.9, 'sota': False},
    {'modelo': 'GPT-4o', 'id_metr': 'gpt_4o_inspect', 'fecha': '2024-05-13', 'p50_min': 7.0, 'ic95_bajo': 4.0, 'ic95_alto': 12.9, 'p80_min': 1.3, 'sota': True},
    {'modelo': 'Claude 3.5 Sonnet (jun 2024)', 'id_metr': 'claude_3_5_sonnet_20240620_inspect', 'fecha': '2024-06-20', 'p50_min': 11.4, 'ic95_bajo': 5.5, 'ic95_alto': 22.4, 'p80_min': 1.7, 'sota': True},
    {'modelo': 'o1-preview', 'id_metr': 'o1_preview', 'fecha': '2024-09-12', 'p50_min': 20.3, 'ic95_bajo': 11.7, 'ic95_alto': 33.4, 'p80_min': 4.4, 'sota': True},
    {'modelo': 'Claude 3.5 Sonnet (oct 2024)', 'id_metr': 'claude_3_5_sonnet_20241022_inspect', 'fecha': '2024-10-22', 'p50_min': 20.5, 'ic95_bajo': 10.1, 'ic95_alto': 40.8, 'p80_min': 2.6, 'sota': True},
    {'modelo': 'o1', 'id_metr': 'o1_inspect', 'fecha': '2024-12-05', 'p50_min': 38.8, 'ic95_bajo': 21.2, 'ic95_alto': 65.0, 'p80_min': 7.1, 'sota': True},
    {'modelo': 'Claude 3.7 Sonnet', 'id_metr': 'claude_3_7_sonnet_inspect', 'fecha': '2025-02-24', 'p50_min': 60.4, 'ic95_bajo': 33.0, 'ic95_alto': 104.2, 'p80_min': 12.1, 'sota': True},
    {'modelo': 'o3', 'id_metr': 'o3_inspect', 'fecha': '2025-04-16', 'p50_min': 119.7, 'ic95_bajo': 74.6, 'ic95_alto': 190.9, 'p80_min': 30.0, 'sota': True},
    {'modelo': 'Claude Opus 4', 'id_metr': 'claude_4_opus_inspect', 'fecha': '2025-05-22', 'p50_min': 100.4, 'ic95_bajo': 60.0, 'ic95_alto': 163.5, 'p80_min': 20.4, 'sota': False},
    {'modelo': 'Claude Opus 4.1', 'id_metr': 'claude_4_1_opus_inspect', 'fecha': '2025-08-05', 'p50_min': 100.5, 'ic95_bajo': 59.3, 'ic95_alto': 159.5, 'p80_min': 23.5, 'sota': False},
    {'modelo': 'GPT-5', 'id_metr': 'gpt_5_2025_08_07_inspect', 'fecha': '2025-08-07', 'p50_min': 203.0, 'ic95_bajo': 112.6, 'ic95_alto': 405.6, 'p80_min': 38.3, 'sota': True},
    {'modelo': 'Gemini 3 Pro', 'id_metr': 'gemini_3_pro', 'fecha': '2025-11-18', 'p50_min': 224.3, 'ic95_bajo': 139.6, 'ic95_alto': 379.2, 'p80_min': 54.1, 'sota': True},
    {'modelo': 'GPT-5.1-Codex-Max', 'id_metr': 'gpt_5_1_codex_max_inspect', 'fecha': '2025-11-19', 'p50_min': 223.7, 'ic95_bajo': 134.3, 'ic95_alto': 396.2, 'p80_min': 50.6, 'sota': False},
    {'modelo': 'Claude Opus 4.5', 'id_metr': 'claude_opus_4_5_inspect', 'fecha': '2025-11-24', 'p50_min': 293.0, 'ic95_bajo': 161.7, 'ic95_alto': 623.7, 'p80_min': 49.4, 'sota': True},
    {'modelo': 'GPT-5.2', 'id_metr': 'gpt_5_2', 'fecha': '2025-12-11', 'p50_min': 352.2, 'ic95_bajo': 198.1, 'ic95_alto': 815.2, 'p80_min': 66.0, 'sota': True},
    {'modelo': 'Claude Opus 4.6', 'id_metr': 'claude_opus_4_6_inspect', 'fecha': '2026-02-05', 'p50_min': 718.8, 'ic95_bajo': 316.7, 'ic95_alto': 3633.8, 'p80_min': 69.9, 'sota': True},
    {'modelo': 'GPT-5.3-Codex', 'id_metr': 'gpt_5_3_codex', 'fecha': '2026-02-05', 'p50_min': 349.5, 'ic95_bajo': 194.9, 'ic95_alto': 816.4, 'p80_min': 54.7, 'sota': False},
    {'modelo': 'Gemini 3.1 Pro', 'id_metr': 'gemini_3_1_pro', 'fecha': '2026-02-19', 'p50_min': 384.1, 'ic95_bajo': 233.5, 'ic95_alto': 694.8, 'p80_min': 89.8, 'sota': False},
    {'modelo': 'GPT-5.4', 'id_metr': 'gpt_5_4', 'fecha': '2026-03-05', 'p50_min': 341.7, 'ic95_bajo': 186.6, 'ic95_alto': 768.8, 'p80_min': 53.9, 'sota': False},
    {'modelo': 'Claude Mythos Preview (temprana)', 'id_metr': 'claude_mythos_preview_early_inspect', 'fecha': '2026-04-07', 'p50_min': 1044.8, 'ic95_bajo': 508.9, 'ic95_alto': 3304.3, 'p80_min': 185.9, 'sota': True},
]

# ---------------------------------------------------------------------------
# 3. PRECIO DE INFERENCIA A CAPACIDAD FIJA (USD por millón de tokens)
# Fuente: Epoch AI, "LLM inference prices have fallen rapidly but unequally across
#   tasks" (Cottier et al., 12/03/2025), https://epoch.ai/data-insights/llm-inference-price-trends
#   CSV https://epoch.ai/data/charts/llm-inference-price-trends/lowest_price_models_data.csv
#   ("Updated Nov. 20, 2025"). Leído 23/11/2026.
# Cada serie: el modelo MÁS BARATO disponible en cada fecha que iguala o supera la
#   puntuación de referencia (GPT-4-0314: 86 en MMLU, 33 en GPQA Diamond; GPT-3.5: 64,8
#   en MMLU). Precio = media ponderada 3:1 de tokens de entrada y salida (metodología de
#   Artificial Analysis, según la página). Fecha = lanzamiento del modelo.
# Cobertura: nov-2022 a feb-2025. Salvedad importante: el dataset NO llega a 2026
#   (último punto: Gemini 2.0 Flash, 05/02/2025). MMLU está saturado como prueba.
# Tasas de la fuente: "the price to achieve GPT-4's performance on a set of PhD-level
#   science questions [GPQA Diamond] fell by 40x per year"; entre todos los umbrales,
#   de 9x a 900x por año, mediana 50x/año; con datos solo desde 2024 la mediana sube a
#   200x/año.
# Cálculo propio (no de Epoch): en MMLU nivel GPT-4, de 37,50 $ (GPT-4, 14/03/2023) a
#   0,175 $ (Gemini 2.0 Flash, 05/02/2025) = 214 veces más barato en ~23 meses.
PRECIO_TASAS_EPOCH = {
    'gpqa_nivel_gpt4_x_por_anio': 40, 'rango_x_por_anio': (9, 900),
    'mediana_x_por_anio': 50, 'mediana_desde_2024_x_por_anio': 200,
}
PRECIO_INFERENCIA = {
    'mmlu_nivel_gpt4': [
        {'fecha': '2023-03-14', 'usd_por_millon': 37.5, 'modelo': 'GPT-4-0314', 'puntuacion': 86.0},
        {'fecha': '2023-11-06', 'usd_por_millon': 15.0, 'modelo': 'GPT-4 Turbo', 'puntuacion': 87.0},
        {'fecha': '2024-05-13', 'usd_por_millon': 7.5, 'modelo': 'GPT-4o-2024-05', 'puntuacion': 87.0},
        {'fecha': '2024-05-23', 'usd_por_millon': 2.19, 'modelo': 'Gemini-1.5-Pro-2024-05', 'puntuacion': 86.0},
        {'fecha': '2025-02-05', 'usd_por_millon': 0.175, 'modelo': 'Gemini 2.0 Flash', 'puntuacion': 88.0},
    ],
    'gpqa_nivel_gpt4': [
        {'fecha': '2023-03-14', 'usd_por_millon': 37.5, 'modelo': 'GPT-4-0314', 'puntuacion': 33.0},
        {'fecha': '2023-11-06', 'usd_por_millon': 15.0, 'modelo': 'GPT-4 Turbo', 'puntuacion': 50.0},
        {'fecha': '2024-02-26', 'usd_por_millon': 6.0, 'modelo': 'Mistral-Large-2024-02', 'puntuacion': 36.0},
        {'fecha': '2024-03-04', 'usd_por_millon': 0.5, 'modelo': 'Claude-3-Haiku', 'puntuacion': 33.0},
        {'fecha': '2024-05-10', 'usd_por_millon': 0.13, 'modelo': 'Gemini-1.5-Flash-2024-05', 'puntuacion': 39.0},
        {'fecha': '2024-12-13', 'usd_por_millon': 0.1225, 'modelo': 'Phi 4', 'puntuacion': 53.0},
    ],
    'mmlu_nivel_gpt35': [
        {'fecha': '2022-11-30', 'usd_por_millon': 20.0, 'modelo': 'GPT-3.5', 'puntuacion': 64.8},
        {'fecha': '2023-03-06', 'usd_por_millon': 2.0, 'modelo': 'GPT-3.5 Turbo', 'puntuacion': 68.0},
        {'fecha': '2023-11-06', 'usd_por_millon': 0.75, 'modelo': 'GPT-3.5-Turbo-2023-11', 'puntuacion': 68.0},
        {'fecha': '2024-03-04', 'usd_por_millon': 0.5, 'modelo': 'Claude-3-Haiku', 'puntuacion': 71.0},
        {'fecha': '2024-05-10', 'usd_por_millon': 0.13, 'modelo': 'Gemini-1.5-Flash-2024-05', 'puntuacion': 79.0},
        {'fecha': '2024-07-23', 'usd_por_millon': 0.1, 'modelo': 'Llama-3.1-Instruct-8B', 'puntuacion': 71.0},
        {'fecha': '2024-10-03', 'usd_por_millon': 0.07, 'modelo': 'Gemini-1.5-Flash-8B', 'puntuacion': 75.0},
    ],
}

# ---------------------------------------------------------------------------
# 4. CAPEX DE LAS GRANDES TECNOLÓGICAS (miles de millones de USD, 1 decimal)
# Fuente: SEC XBRL companyconcept API, us-gaap, formularios 10-K, periodos de ~12 meses,
#   valor del 10-K más reciente que reporta cada año. Leído 23/11/2026.
#   Microsoft  https://data.sec.gov/api/xbrl/companyconcept/CIK0000789019/us-gaap/PaymentsToAcquirePropertyPlantAndEquipment.json
#   Alphabet   https://data.sec.gov/api/xbrl/companyconcept/CIK0001652044/us-gaap/PaymentsToAcquirePropertyPlantAndEquipment.json
#   Meta       https://data.sec.gov/api/xbrl/companyconcept/CIK0001326801/us-gaap/PaymentsToAcquirePropertyPlantAndEquipment.json
#   Amazon     https://data.sec.gov/api/xbrl/companyconcept/CIK0001018724/us-gaap/PaymentsToAcquireProductiveAssets.json
# Concepto: pagos en efectivo por inmovilizado ("Purchases of property and equipment").
#   Amazon usa PaymentsToAcquireProductiveAssets (compras BRUTAS, incl. software de uso
#   interno, sin restar incentivos ni ventas). Para Amazon 2015 no hay valor con esa
#   presentación en XBRL (None); con la presentación antigua, neta de incentivos
#   (PaymentsToAcquirePropertyPlantAndEquipment), 2015 = 4,6 y 2016 = 6,7 (vs 7,8 bruto).
# Años: Alphabet, Amazon y Meta, año natural. Microsoft, AÑO FISCAL que acaba el 30 de
#   junio (FY2026 = jul-2025 a jun-2026); por eso tiene 2026 completo.
# Salvedad: NINGUNA serie incluye arrendamientos financieros (finance leases), que en
#   Microsoft y Meta ya son grandes; las guías de abajo sí los incluyen en esos dos.
CAPEX_ANUAL = {
    'microsoft': {2015: 5.9, 2016: 8.3, 2017: 8.1, 2018: 11.6, 2019: 13.9, 2020: 15.4,
                  2021: 20.6, 2022: 23.9, 2023: 28.1, 2024: 44.5, 2025: 64.6, 2026: 115.9},
    'alphabet':  {2015: 10.0, 2016: 10.2, 2017: 13.2, 2018: 25.1, 2019: 23.5, 2020: 22.3,
                  2021: 24.6, 2022: 31.5, 2023: 32.3, 2024: 52.5, 2025: 91.4},
    'amazon':    {2015: None, 2016: 7.8, 2017: 12.0, 2018: 13.4, 2019: 16.9, 2020: 40.1,
                  2021: 61.1, 2022: 63.6, 2023: 52.7, 2024: 83.0, 2025: 131.8},
    'meta':      {2015: 2.5, 2016: 4.5, 2017: 6.7, 2018: 13.9, 2019: 15.1, 2020: 15.2,
                  2021: 18.7, 2022: 31.2, 2023: 27.0, 2024: 37.3, 2025: 69.7},
}
# 2026 hasta la fecha (10-Q en la misma API y concepto):
CAPEX_2026_ACUMULADO = {
    'alphabet': {'periodo': 'ene-sep 2026', 'valor': 132.0},             # 131.95; 10-Q 29/10/2026
    'amazon':   {'periodo': 'ene-sep 2026', 'valor': 175.7},             # 175.67 bruto; 10-Q 30/10/2026
    'meta':     {'periodo': 'ene-sep 2026', 'valor': 83.1},              # 83.06; 10-Q 22/10/2026
    'microsoft_fy2027_t1': {'periodo': 'jul-sep 2026', 'valor': 39.4},   # 39.37; 10-Q 28/10/2026
    # DERIVADO (suma de cifras XBRL): Microsoft ene-sep 2026 = 30.88 (ene-mar) +
    # 35.80 (abr-jun = FY26 115.95 - 9M FY26 80.15) + 39.37 (jul-sep) = 106.1
    'microsoft_derivado': {'periodo': 'ene-sep 2026', 'valor': 106.1},
}
# Guía oficial para el año natural 2026 (resultados del 3T 2026). Ojo: definiciones distintas.
CAPEX_GUIA_2026 = {
    'alphabet': {'rango': (195, 205), 'definicion': 'CapEx',
                 'fecha': '2026-10-28',
                 'fuente': 'https://s206.q4cdn.com/479360582/files/doc_events/2026/Oct/28/2026_Q3_Earnings_Transcript.pdf',
                 'cita': 'our fullyear 2026 CapEx guidance range of $195-$205 billion remain unchanged'},
    'amazon':   {'valor': 220, 'definicion': 'cash capital expenditures (Amazon la define neta de incentivos)',
                 'fecha': '2026-10-29',
                 'fuente': 'https://aboutamazon.com/news/company-news/amazon-earnings-q3-2026-report',
                 'cita': 'We continue to expect 2026 cash capital expenditures to be approximately $220 billion.'},
    'meta':     {'rango': (135, 145), 'definicion': 'incluye pagos de principal de arrendamientos financieros',
                 'fecha': '2026-10-21',
                 'fuente': 'https://investor.atmeta.com/investor-news/press-release-details/2026/Meta-Reports-Third-Quarter-2026-Results/default.aspx',
                 'cita': 'in the range of $135-145 billion, narrowed from our prior outlook of $130-145 billion'},
    'microsoft': {'valor': 170, 'definicion': 'año natural 2026; capex incluye arrendamientos financieros',
                  'fecha': '2026-10-28',
                  'fuente': 'https://www.microsoft.com/en-us/investor/events/fy-2027/earnings-fy-2027-q1',
                  'cita': 'for the calendar year, spend should be approximately $170 billion'},
}
# Suma de las cuatro guías (cálculo propio, puntos medios): 200 + 220 + 140 + 170 = 730.

# ---------------------------------------------------------------------------
# 5. CONSUMO ELÉCTRICO DE LOS CENTROS DE DATOS (TWh)
# Fuente principal (actualización de 2026): IEA, "Key Questions on Energy and AI"
#   (publicado 16/04/2026), https://www.iea.org/reports/key-questions-on-energy-and-ai/executive-summary
#   datos del gráfico https://www.iea.org/data-and-statistics/charts/electricity-consumption-by-data-centres-2020-2035
#   Leído 23/11/2026. Histórico 2020-2025; caso base 2026-2035; banda = rango entre casos.
# Fuente original (abril 2025): IEA, "Energy and AI", https://www.iea.org/reports/energy-and-ai/energy-demand-from-ai
#   gráfico https://www.iea.org/data-and-statistics/charts/global-data-centre-electricity-consumption-by-sensitivity-case-2020-2035
# Cuota del consumo eléctrico mundial (textos de la IEA): ~1,5 % en 2024 (415 TWh);
#   ~3 % en 2030 (actualización 2026: "around 3% of global electricity demand").
#   Escenarios 2035 del informe de 2025: Lift-Off ~4,4 % (>1.700 TWh), High Efficiency
#   2,6 % (~970 TWh), Headwinds <2 % (~700 TWh). No hallé en lo leído la cuota del caso
#   base en 2035.
# Datos citables: +17 % en 2025 (~70 TWh) según la IEA (Global Energy Review 2026 y Key
#   Questions); los centros de datos dedicados a IA crecieron un 50 % en 2025; ~12 %/año
#   desde 2017; en 2030, "slightly more than Japan's total electricity consumption today".
CENTROS_DATOS_TWH = {
    'historico': {2020: 269.1, 2021: 297.0, 2022: 324.1, 2023: 360.4, 2024: 415.6, 2025: 485.1},
    'caso_base': {2026: 560.0, 2027: 664.4, 2028: 773.0, 2029: 862.4, 2030: 945.0,
                  2031: 1012.5, 2032: 1075.0, 2033: 1119.3, 2034: 1161.5, 2035: 1192.9},
    # Banda de escenarios (área apilada del gráfico: inferior = 'Blank'; superior = Blank + 'Case range')
    'rango_inferior': {2026: 548.6, 2027: 639.9, 2028: 711.4, 2029: 772.5, 2030: 832.8,
                       2031: 868.1, 2032: 894.9, 2033: 912.5, 2034: 934.7, 2035: 942.0},
    'rango_superior': {2026: 559.9, 2027: 664.3, 2028: 772.9, 2029: 885.5, 2030: 1008.3,
                       2031: 1130.8, 2032: 1264.2, 2033: 1394.9, 2034: 1527.1, 2035: 1636.9},
}
# Escenarios del informe de abril de 2025 (para comparar; su histórico acaba en 2024):
CENTROS_DATOS_TWH_IEA2025 = {
    'historico': {2020: 269, 2021: 297, 2022: 324, 2023: 361, 2024: 416},
    'base': {2025: 485, 2026: 560, 2027: 665, 2028: 773, 2029: 863, 2030: 946,
             2031: 1013, 2032: 1076, 2033: 1120, 2034: 1162, 2035: 1193},
    'lift_off': {2030: 1264, 2035: 1719},
    'high_efficiency': {2030: 792, 2035: 972},
    'headwinds': {2030: 669, 2035: 707},
}
CENTROS_DATOS_CUOTA = {2024: 1.5, 2030: 3.0}  # % del consumo eléctrico mundial, caso base

# ---------------------------------------------------------------------------
# 6. ADOPCIÓN: USUARIOS SEMANALES DE CHATGPT (millones)
# Cifras anunciadas por OpenAI o sus directivos; cada punto con la URL leída el 23/11/2026.
# Fecha = la del anuncio (o de la publicación que lo recoge), no la de la medición.
CHATGPT_USUARIOS_SEMANALES = [
    {'fecha': '2023-11-06', 'millones': 100, 'quien': 'Sam Altman, DevDay 2023',
     'fuente': 'https://techcrunch.com/2023/11/06/openais-chatgpt-now-has-100-million-weekly-active-users/'},
    {'fecha': '2024-08-29', 'millones': 200, 'quien': 'OpenAI (portavoz a Axios/The Verge): "more than 200 million"',
     'fuente': 'https://www.theverge.com/2024/8/29/24231685/openai-chatgpt-200-million-weekly-users'},
    {'fecha': '2024-12-04', 'millones': 300, 'quien': 'Sam Altman, NYT DealBook Summit',
     'fuente': 'https://www.theverge.com/2024/12/4/24313097/chatgpt-300-million-weekly-users'},
    {'fecha': '2025-02-20', 'millones': 400, 'quien': 'Brad Lightcap (COO) a CNBC',
     'fuente': 'https://www.cnbc.com/2025/02/20/openai-tops-400-million-users-despite-deepseeks-emergence.html'},
    {'fecha': '2025-03-31', 'millones': 500, 'quien': 'OpenAI, "New funding to build towards AGI"',
     'fuente': 'https://openai.com/index/march-funding-updates/'},
    {'fecha': '2025-09-15', 'millones': 700, 'quien': 'OpenAI, "How people are using ChatGPT"',
     'fuente': 'https://openai.com/index/how-people-are-using-chatgpt/'},
    {'fecha': '2025-10-06', 'millones': 800, 'quien': 'Sam Altman, DevDay 2025',
     'fuente': 'https://techcrunch.com/2025/10/06/sam-altman-says-chatgpt-has-hit-800m-weekly-active-users/'},
    {'fecha': '2026-02-27', 'millones': 900, 'quien': 'OpenAI: "more than 900M weekly active users"',
     'fuente': 'https://openai.com/index/scaling-ai-for-everyone/'},
    {'fecha': '2026-09-29', 'millones': 1200, 'quien': 'OpenAI, recap de DevDay 2026: "our collective 1.2B weekly users"',
     'fuente': 'https://openai.com/index/devday-2026-recap/', 'comparable': False},
]
# Salvedades:
# - El punto de 1.200 M NO es estrictamente comparable: OpenAI escribe "our collective
#   1.2B weekly users", sin decir "ChatGPT" ni "active"; puede sumar Codex y otros
#   productos. Para una serie limpia, terminar en 900 M (feb-2026).
# - 31/07/2026: OpenAI dijo "Our models now reach more than one billion active users"
#   (AFP, https://www.bnnbloomberg.ca/business/artificial-intelligence/2026/07/31/openai-says-has-more-than-1-billion-active-users/),
#   sin "weekly" y para todos sus productos: no se incluye.
# - El ~1.000 M semanal de solo ChatGPT a mediados de 2026 lo publicó The Information a
#   partir de cifras internas, no OpenAI: no se incluye.
# - 500 M y 700 M van en páginas de OpenAI como "people who use ChatGPT every week" y
#   "weekly active users"; 300 M, como "people using the AI chatbot each week".

# Opcional. Census Bureau, Business Trends and Outlook Survey (BTOS), EE. UU., nacional.
# Fichero: https://www.census.gov/hfp/btos/downloads/National.xlsx (hoja "Response
#   Estimates", pregunta 7, respuesta "Yes"; fechas de la hoja "Collection and Reference
#   Dates"), leído 23/11/2026.
# Pregunta (redacción del fichero, tal cual): "In the last two weeks, did this business
#   use Super Intelligence or SI (formerly referred to as Artificial Intelligence or AI)
#   in any of its business functions?". Fecha = fin del periodo de referencia (2 semanas).
# Salvedades: esta pregunta empieza en el ciclo 202524 (ref. 03-16/11/2025); la serie de
#   2023-2025 con la pregunta antigua no está en este fichero y no sería comparable. Sin
#   datos 202521-202523 por el cierre del Gobierno federal (oct-nov 2025). Último dato:
#   ciclo 202623, publicado el 19/11/2026. La pregunta 8 (empleados que usan IA
#   generativa) solo tiene dos ciclos: 26,8 % y 27,6 %.
BTOS_EMPRESAS_USAN_IA = [  # (fecha, % de empresas)
    ('2025-11-16', 17.3), ('2025-11-30', 17.2), ('2025-12-14', 17.8), ('2025-12-28', 17.7),
    ('2026-01-11', 18.2), ('2026-01-25', 18.9), ('2026-02-08', 17.5), ('2026-02-22', 18.2),
    ('2026-03-08', 18.9), ('2026-03-22', 19.1), ('2026-04-05', 19.8), ('2026-04-19', 19.8),
    ('2026-05-03', 19.5), ('2026-05-17', 20.6), ('2026-05-31', 20.6), ('2026-06-14', 20.6),
    ('2026-06-28', 21.7), ('2026-07-12', 21.5), ('2026-07-26', 21.8), ('2026-08-09', 22.4),
    ('2026-08-23', 23.2), ('2026-09-06', 23.8), ('2026-09-20', 23.8), ('2026-10-04', 24.6),
    ('2026-10-18', 24.2), ('2026-11-01', 25.0),
]


# Texto del modal de la «i» de cada gráfica (párrafos separados por línea en blanco).
INFO_GRAFICAS = {
    'computo':
        'Entrenar un modelo de IA es hacerle leer enormes cantidades de datos y ajustar sus miles de millones de parámetros, y eso se mide en operaciones de cálculo: FLOP. Un FLOP es una suma o una multiplicación con decimales.\n\n'
        'El eje vertical es logarítmico: cada raya multiplica por 1.000. Una línea que sube recta en esta escala significa crecimiento exponencial. Según Epoch AI, el cómputo de los modelos de lenguaje punteros se multiplica por unas cinco veces cada año desde 2020.\n\n'
        'Importa porque, hasta ahora, más cómputo ha traído modelos más capaces de forma bastante predecible. También explica la factura: el centro de datos, los chips y la electricidad que hacen falta crecen al mismo ritmo. Muchas cifras son estimaciones de Epoch, porque las empresas ya casi no las publican.',
    'horizonte':
        'METR, una organización que evalúa modelos de IA, mide qué tareas logra completar un agente de IA por su cuenta: programar, depurar, investigar un problema. Cada tarea se calibra con el tiempo que le lleva a un experto humano.\n\n'
        'El «horizonte» de un modelo es la duración de las tareas que completa la mitad de las veces. Si es de una hora, resuelve con un 50 % de éxito tareas que a una persona experta le toman una hora.\n\n'
        'Es probablemente la medida más reveladora de hacia dónde va la IA: no mide si responde bien a una pregunta, sino cuánto trabajo puede hacer sola. Ojo: METR advierte que por encima de unas 16 horas sus tareas no bastan para medir bien, y el margen de error de los últimos modelos es muy amplio. Dejó de actualizar esta página en septiembre de 2026.',
    'precio':
        'Cada línea sigue el modelo más barato que alcanza una misma nota en una prueba: la que sacaba GPT-4 en MMLU (preguntas de 57 materias), la que sacaba en GPQA Diamond (ciencia de nivel doctorado) y la que sacaba GPT-3.5 en MMLU. El precio es el de un millón de tokens (unas 750.000 palabras) mezclando lectura y escritura.\n\n'
        'El eje es logarítmico: cada raya divide el precio por 10. Epoch AI calcula que, según el nivel, la misma capacidad se abarata entre 9 y 900 veces por año.\n\n'
        'Importa porque lo que hace dos años solo podía pagar una gran empresa hoy cuesta céntimos, y eso cambia quién puede usar la IA y para qué. Los datos de Epoch llegan a febrero de 2025.',
    'capex':
        'El «capex» (inversión de capital) es lo que una empresa gasta en activos que durarán años: edificios, servidores, chips, redes. En estas cuatro empresas hoy es sobre todo centros de datos para IA.\n\n'
        'La gráfica suma los pagos en efectivo que declaran a la SEC, el regulador bursátil de EE. UU. Microsoft cuenta por años fiscales que acaban en junio. La barra de 2026 es distinta: suma lo que cada empresa dice que gastará en el año, y cada una lo define a su manera (Microsoft y Meta incluyen arrendamientos), así que es orientativa.\n\n'
        'Importa por su tamaño: estas cuatro empresas invierten al año más que el PIB de muchos países, y ese dinero se convierte en demanda de chips, electricidad y agua.',
    'electricidad':
        'Los centros de datos son edificios llenos de servidores que funcionan día y noche y que hay que enfriar. La IA multiplica su consumo: entrenar y usar modelos grandes exige chips que gastan mucha más energía que un servidor normal.\n\n'
        'La gráfica es de la Agencia Internacional de la Energía (AIE). Hasta 2025 son datos; desde ahí, su caso base, con la franja que cubren sus escenarios alternativos. En 2030 los centros de datos consumirían algo más que todo Japón hoy.\n\n'
        'Es el puente con el cambio climático: según cómo se genere esa electricidad, la IA puede empujar al alza las emisiones o acelerar la inversión en renovables y nuclear. A escala local tensa las redes eléctricas y el agua donde se concentran.',
    'usuarios':
        'La gráfica recoge las cifras de usuarios semanales de ChatGPT que ha anunciado OpenAI: personas que lo usaron al menos una vez en la semana. Son cifras de la empresa, sin auditoría externa.\n\n'
        'Pasó de 100 millones a finales de 2023 a más de 900 millones a comienzos de 2026: más de una de cada diez personas del planeta. Ninguna tecnología de consumo se había extendido tan rápido.\n\n'
        'La serie se corta en febrero de 2026 a propósito. En septiembre OpenAI habló de 1.200 millones de usuarios semanales, pero sumando todos sus productos, no solo ChatGPT, así que no es comparable.',
}


def _anio_decimal(fecha):
    """'2023-03-14' → 2023.2 (aprox.), para los ejes de las nubes de puntos."""
    anio, mes, dia = (int(p) for p in fecha.split('-'))
    return round(anio + (mes - 1) / 12 + (dia - 1) / 365, 3)


def _fecha_larga(fecha):
    anio, mes, dia = fecha.split('-')
    return f'{MESES[int(mes) - 1]} de {anio}'


def _duracion(minutos):
    """Minutos → '17 horas', '45 minutos'."""
    if minutos >= 90:
        return f'{_coma(minutos / 60, 0)} horas'
    return f'{_coma(minutos, 0)} minutos'


def _miles(valor):
    return f'{round(valor):,}'.replace(',', '.')


def _modelo(nombre):
    return next(m for m in COMPUTO_ENTRENAMIENTO if m['modelo'].startswith(nombre))


def _guia_2026():
    """Punto medio de la previsión de cada empresa para 2026."""
    return {k: (sum(g['rango']) / 2 if 'rango' in g else g['valor']) for k, g in CAPEX_GUIA_2026.items()}


def resumen():
    record = max(COMPUTO_ENTRENAMIENTO, key=lambda m: m['flop'])
    gpt4 = _modelo('GPT-4')
    gpt3 = _modelo('GPT-3 175B')

    medidos = [m for m in HORIZONTE_METR if m['p50_min']]
    mejor = max(medidos, key=lambda m: m['p50_min'])
    gpt4_h = next(m for m in HORIZONTE_METR if m['modelo'] == 'GPT-4')

    precio = PRECIO_INFERENCIA['mmlu_nivel_gpt4']

    anios_capex = sorted({a for v in CAPEX_ANUAL.values() for a in v if a <= 2025})
    total = lambda a: sum((v.get(a) or 0) for v in CAPEX_ANUAL.values())
    ultimo_capex = max(a for a in anios_capex if all(v.get(a) for v in CAPEX_ANUAL.values()))
    guia = sum(_guia_2026().values())

    twh = CENTROS_DATOS_TWH
    ultimo_twh = max(twh['historico'])

    usuarios = [u for u in CHATGPT_USUARIOS_SEMANALES if u.get('comparable', True)]

    return {
        'computo_record': record['modelo'],
        'computo_record_fecha': _fecha_larga(record['fecha']),
        'computo_vs_gpt4': _miles(record['flop'] / gpt4['flop']),
        'computo_vs_gpt3': _miles(round(record['flop'] / gpt3['flop'], -2)),
        'computo_multiplicador': COMPUTO_TASA_EPOCH['multiplicador_anual'],
        'computo_duplicacion': _coma(COMPUTO_TASA_EPOCH['duplicacion_meses'], 1),

        'horizonte_mejor': mejor['modelo'],
        'horizonte_mejor_valor': _duracion(mejor['p50_min']),
        'horizonte_gpt4': _duracion(gpt4_h['p50_min']),
        'horizonte_duplicacion': _coma(HORIZONTE_DUPLICACION['desde_2023_dias'] / 30.44, 0),

        'precio_inicio': _coma(precio[0]['usd_por_millon'], 2),
        'precio_inicio_modelo': precio[0]['modelo'].split('-0')[0],
        'precio_inicio_fecha': _fecha_larga(precio[0]['fecha']),
        'precio_fin': _coma(precio[-1]['usd_por_millon'], 3).rstrip('0'),
        'precio_fin_modelo': precio[-1]['modelo'],
        'precio_fin_fecha': _fecha_larga(precio[-1]['fecha']),
        'precio_veces': round(precio[0]['usd_por_millon'] / precio[-1]['usd_por_millon']),

        'capex_anio': ultimo_capex,
        'capex_total': _miles(total(ultimo_capex)),
        'capex_anterior': _miles(total(ultimo_capex - 1)),
        'capex_2020': _miles(total(2020)),
        'capex_guia': _miles(guia),

        'twh_anio': ultimo_twh,
        'twh_valor': _miles(twh['historico'][ultimo_twh]),
        'twh_crecimiento': _coma((twh['historico'][ultimo_twh] / twh['historico'][ultimo_twh - 1] - 1) * 100, 0),
        'twh_2030': _miles(twh['caso_base'][2030]),
        'twh_2035': _miles(twh['caso_base'][2035]),
        'twh_cuota_2024': _coma(CENTROS_DATOS_CUOTA[2024], 1),
        'twh_cuota_2030': _coma(CENTROS_DATOS_CUOTA[2030], 0),

        'usuarios_ultimo': _miles(usuarios[-1]['millones']),
        'usuarios_ultimo_fecha': _fecha_larga(usuarios[-1]['fecha']),
        'usuarios_primero': _miles(usuarios[0]['millones']),
        'usuarios_primero_fecha': _fecha_larga(usuarios[0]['fecha']),
    }


def contexto():
    anios_capex = list(range(2016, 2026))  # Amazon no tiene 2015 en la misma presentación
    guia = _guia_2026()
    twh = CENTROS_DATOS_TWH
    anios_twh = sorted({**twh['historico'], **twh['caso_base']})
    ultimo_historico = max(twh['historico'])
    return {
        'resumen': resumen(),
        'info': INFO_GRAFICAS,
        'datos_graficas': {
            'retos-computo': [
                {'x': _anio_decimal(m['fecha']), 'y': m['flop'], 'modelo': m['modelo'],
                 'fecha': m['fecha'], 'frontera': m['frontera']}
                for m in COMPUTO_ENTRENAMIENTO
            ],
            'retos-horizonte': [
                {'x': _anio_decimal(m['fecha']), 'y': m['p50_min'], 'modelo': m['modelo'],
                 'fecha': m['fecha'], 'bajo': m['ic95_bajo'], 'alto': m['ic95_alto'], 'sota': m['sota']}
                for m in HORIZONTE_METR if m['p50_min']
            ],
            'retos-precio': {
                clave: [{'x': _anio_decimal(p['fecha']), 'y': p['usd_por_millon'], 'modelo': p['modelo'],
                         'fecha': p['fecha']} for p in puntos]
                for clave, puntos in PRECIO_INFERENCIA.items()
            },
            'retos-capex': {
                'anios': [str(a) for a in anios_capex] + ['2026 (previsión)'],
                **{k: [v.get(a) for a in anios_capex] + [guia[k]] for k, v in CAPEX_ANUAL.items()},
            },
            'retos-electricidad': {
                'anios': anios_twh,
                'historico': [twh['historico'].get(a) for a in anios_twh],
                # La proyección arranca en el último dato medido para que las dos líneas se toquen.
                'caso_base': [twh['historico'][a] if a == ultimo_historico else twh['caso_base'].get(a)
                              for a in anios_twh],
                'bajo': [twh['rango_inferior'].get(a) for a in anios_twh],
                'alto': [twh['rango_superior'].get(a) for a in anios_twh],
            },
            'retos-usuarios': [
                {'x': _anio_decimal(u['fecha']), 'y': u['millones'], 'fecha': u['fecha']}
                for u in CHATGPT_USUARIOS_SEMANALES if u.get('comparable', True)
            ],
        },
    }
