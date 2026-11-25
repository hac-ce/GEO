# 判断文本是否包含品牌名称或任一别名。
def mentions(text: str, names: list[str]) -> bool:
    text = text.casefold()
    for name in names:
        name = name.strip().casefold()
        if not name :
            continue
        if name in text:
            return True
    return False

# 分析回答是否提及品牌，以及问题是否已点名品牌。
def evaluate(
    answer: str,
    question: str,
    brand_name: str,
    aliases: list[str]
) -> dict:
    names = [brand_name] + aliases
    mentioned = mentions(answer, names)
    prompted = mentions(question, names)
    return {
        "mentioned": mentioned,
        "prompted": prompted
    }


# 根据已保存的分析结果计算自然提及率，排除未知和问题点名品牌的样本。
def summarize(samples: list[dict]) -> dict:
    total_samples = len(samples)
    eligible_samples = 0
    mentioned_samples = 0
    for sample in samples:
        if sample["mentioned"] is None or sample["prompted"] is None:
            continue
        if sample["prompted"] is True:
            continue
        eligible_samples += 1
        if sample["mentioned"] is True:
            mentioned_samples += 1
    if eligible_samples > 0:
        mention_rate = mentioned_samples / eligible_samples
    else:
        mention_rate = None
    return {
        "total_samples": total_samples,
        "eligible_samples": eligible_samples,
        "mentioned_samples": mentioned_samples,
        "mention_rate": mention_rate
    }
