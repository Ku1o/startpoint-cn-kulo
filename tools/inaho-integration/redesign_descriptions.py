"""Per-condition player copy, using the same description override reader as author characters.

Use ordinary source terms so SkillReplaceString controls the graphical switch.
All balance amounts are read from the final rows, rather than duplicated constants.
"""


def number(value):
    return f'{value:g}'


def strength(row, col=51):
    assert row[col] == row[col + 1]
    return int(row[col]) / 100000


def percent(row, col=51):
    return number(strength(row, col) * 100) + '%'


def maximum(row, col=51, limit=34):
    return number(strength(row, col) * 100 * int(row[limit])) + '%'


def seconds(row, col=57):
    return number(strength(row, col) / 60) + '秒'


def descriptions(abilities, leaders):
    a = [abilities[str(1599910 + n)] for n in range(1, 7)]
    l = leaders['159991']
    main = '作为主要角色编成：'
    resonance = '光属性共鸣时，'
    text = {
        'cnmod_inaho_midautumn': [
            f'光属性角色攻击力＋{percent(l[0],49)}、技能伤害＋{percent(l[1],49)}、能力伤害＋{percent(l[2],49)}',
            f'战斗开始时，赋予队伍全体贯穿、浮游效果（{seconds(l[3],55)}），赋予自身再生效果[恢复{number(strength(l[5],49))}]（{seconds(l[5],55)}）',
            f'Fever模式中，光属性角色直接攻击伤害＋{percent(l[6],111)}',
            f'自身回复生命值时，光属性角色攻击力＋{percent(l[7],49)}[最大＋{maximum(l[7],49,32)}]',
            resonance + f'自身每发动{number(int(l[8][28])/100000)}次能力攻击，对全场敌人造成自身攻击力{number(strength(l[8],49))}倍威力的光属性能力伤害，并赋予自身攻击力＋{percent(l[9],49)}、能力伤害＋{percent(l[10],49)}（{seconds(l[9],55)}，冷却时间：0.02秒）',
            f'「月满丰穰」期间，每达成45连击，赋予队伍全体贯穿、浮游效果（{seconds(l[11],55)}），自身技能槽＋{percent(l[15],49)}',
            resonance + f'Fever模式中，自身回复生命值时，队伍全体技能槽＋{percent(l[14],49)}（冷却时间：{number(int(l[14][33])/60)}秒）',
            resonance + '「月满丰穰」期间，自身不会被赋予弱化效果',
            '强化弹射Lv1／Lv2／Lv3时，赋予队伍全体攻击力＋20%／＋40%／＋80%（3／5／8秒）及浮游、贯穿效果（1／3／5秒）',
            '强化弹射Lv3时，对全场敌人追加队长当前攻击力28倍威力的光属性强化弹射伤害（1段）',
        ],
        'cnmod_inaho_midautumn_1': [
            main + f'战斗开始时，队伍全体技能槽＋{percent(a[0][0])}、攻击力＋{percent(a[0][2])}，赋予再生效果[恢复{number(strength(a[0][1]))}]（{seconds(a[0][1])}）',
            main + f'战斗开始时，赋予光属性角色技能伤害＋{percent(a[0][3])}（{seconds(a[0][3])}）',
            f'自身回复生命值时，Fever＋{number(strength(a[0][7]))}',
            main + f'自身发动技能时，自身技能槽＋{percent(a[0][4])}（最多{a[0][4][34]}次）；光属性共鸣时，队伍全体另获得技能槽＋{percent(a[0][5])}（最多{a[0][5][34]}次）',
            main + f'「月行」期间，自身冲刺冷却时间{percent(a[0][6],113)}',
        ],
        'cnmod_inaho_midautumn_2': [
            main + f'队伍全体直接攻击伤害＋{percent(a[1][0])}、对敌人造成的直接攻击伤害额外乘区＋{percent(a[1][4])}',
            main + f'Fever模式中，强化队伍全体的直接攻击[直接攻击计算为3次／合计伤害＋{percent(a[1][1],113)}]',
            main + f'队伍角色直接攻击时，对最近的敌人造成自身攻击力{number(strength(a[1][2]))}倍威力的光属性能力伤害（冷却时间：{number(int(a[1][2][35])/60)}秒）',
            main + resonance + f'Fever模式中，自身回复生命值时，队伍全体攻击力＋{percent(a[1][3])}[最大＋{maximum(a[1][3])}]，自身能力伤害＋{percent(a[1][5])}[最大＋{maximum(a[1][5])}]',
        ],
        'cnmod_inaho_midautumn_3': [
            main + f'队伍全体技能伤害＋{percent(a[2][0])}',
            main + f'Fever模式中，队伍全体能力伤害＋{percent(a[2][1],113)}、对敌人造成的伤害额外乘区＋{percent(a[2][2],113)}',
            main + f'自身发动技能时，自身攻击力＋{percent(a[2][5])}[最大＋{maximum(a[2][5])}]，队伍全体技能伤害＋{percent(a[2][4])}[最大＋{maximum(a[2][4])}]',
            main + f'光属性角色每发动能力攻击，队伍全体攻击力＋{percent(a[2][6])}[最大＋{maximum(a[2][6])}]、对敌人造成的能力伤害额外乘区＋{percent(a[2][7])}[最大＋{maximum(a[2][7])}]',
            main + resonance + f'Fever模式中，光属性角色每发动能力攻击，队伍全体对弱化效果中的敌人造成的伤害＋{percent(a[2][3])}[最大＋{maximum(a[2][3])}]',
        ],
        'cnmod_inaho_midautumn_4': [
            f'队伍全体对弱化效果中的敌人造成的伤害＋{percent(a[3][0])}、弱化效果时间＋{percent(a[3][1])}',
            f'自身回复生命值时，对最近的敌人造成自身攻击力{number(strength(a[3][2]))}倍威力的光属性能力伤害（冷却时间：{number(int(a[3][2][35])/60)}秒）',
            resonance + f'队伍全体暗属性抗性＋{percent(a[3][3])}',
            main + resonance + '强化「月满丰穰」：攻击力、能力伤害、直接攻击伤害的提升量各＋100%，技能伤害的提升量＋50%',
        ],
        'cnmod_inaho_midautumn_5': [
            f'光属性角色攻击力＋{percent(a[4][0])}、技能伤害＋{percent(a[4][1])}',
            resonance + f'队伍全体对敌人造成的伤害额外乘区＋{percent(a[4][2])}',
            resonance + f'Fever模式中，自身回复生命值时，队伍全体直接攻击伤害＋{percent(a[4][3])}[最大＋{maximum(a[4][3])}]',
            f'光属性角色回复生命值时，Fever＋{number(strength(a[4][4]))}',
        ],
        'cnmod_inaho_midautumn_6': [
            f'Fever模式中，队伍全体攻击力＋{percent(a[5][0],113)}、技能伤害＋{percent(a[5][1],113)}',
            f'队伍全体强化效果时间＋{percent(a[5][2])}',
            resonance + f'光属性角色技能充能速度＋{percent(a[5][3])}、Fever获取量＋{percent(a[5][8])}，Fever模式时间＋{percent(a[5][4])}',
            f'进入Fever模式时，赋予队伍全体再生效果[恢复{number(strength(a[5][6]))}]（{seconds(a[5][6])}）及技能伤害＋{percent(a[5][5])}（{seconds(a[5][5])}）',
            main + resonance + '强化『月满稻穗·星屑幻梦』的伤害效果[合计75倍，共3段]',
        ],
    }
    for lines in text.values():
        assert all(lines) and all('<icon' not in line for line in lines)
    return {'desc_override_' + key: '\n'.join(lines) for key, lines in text.items()}
