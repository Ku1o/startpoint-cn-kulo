"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.serializePlayerData = void 0;
const date_1 = require("./date");
const serialize_entities_1 = require("./serialize-entities");
const utils_1 = require("../../utils");
const types_1 = require("../types");
const asset_1 = require("../../routes/api/asset");
const rushEvent_1 = require("../domains/rushEvent");
const mission_1 = require("../domains/mission");
const player_1 = require("../domains/player");
const mail_1 = require("../domains/mail");
const codeMap_1 = require("../codeMap");
const stamina_1 = require("../../lib/stamina");
const mode15_optional_1 = require("../../lib/mode15-optional");
const start_tutorial_state_1 = require("../../lib/start-tutorial-state");
function clearSerializedPlayedPartyMembers(party) {
    party.character_id_1 = party.character_id_2 = party.character_id_3 = null;
    party.unison_character_id_1 = party.unison_character_id_2 = party.unison_character_id_3 = null;
    party.evolution_img_level_1 = party.evolution_img_level_2 = party.evolution_img_level_3 = null;
    party.unison_evolution_img_level_1 = party.unison_evolution_img_level_2 = party.unison_evolution_img_level_3 = null;
}
/**
 * Serializes a player data object in the way that the world flipper client expects it.
 *
 * @param player The player data object to serialize.
 * @returns A serialized player data object.
 */
function serializePlayerData(toSerialize, options) {
    var _a, _b, _c, _d, _e, _f;
    // convert userCharacterList (k_id → business code)
    const userCharacterList = {};
    for (const [characterId, character] of Object.entries(toSerialize.characterList)) {
        const kId = parseInt(characterId);
        const code = (0, codeMap_1.kIdToBusinessCode)(kId);
        const codeKey = String(code);
        // convert bond tokens
        const bondTokenList = (0, serialize_entities_1.serializeBondTokenStatuses)(character.bondTokenList);
        const converted_character = {
            "entry_count": character.entryCount,
            "evolution_level": character.evolutionLevel,
            "over_limit_step": character.overLimitStep,
            "protection": character.protection,
            "join_time": (0, utils_1.getServerTime)(character.joinTime),
            "update_time": (0, utils_1.getServerTime)(character.updateTime),
            "exp": character.exp,
            "stack": character.stack,
            "bond_token_list": bondTokenList,
            "mana_board_index": character.manaBoardIndex
        };
        const exBoost = character.exBoost;
        if (exBoost !== undefined) {
            converted_character['ex_boost'] = {
                "status_id": exBoost.statusId,
                "ability_id_list": exBoost.abilityIdList
            };
        }
        if (character.illustrationSettings !== undefined) {
            converted_character['illustration_settings'] = character.illustrationSettings;
        }
        // Set mana_board_awake from actual node awake levels (post-awakening data, not mission-based)
        const manaBoard = (_a = toSerialize.manaBoardAwakeMap) === null || _a === void 0 ? void 0 : _a.get(characterId);
        if (manaBoard) {
            converted_character.mana_board_awake = manaBoard;
        }
        userCharacterList[codeKey] = converted_character;
    }
    // convert parties
    const userPartyGroupList = (0, serialize_entities_1.serializePartyGroupList)(toSerialize.partyGroupList);
    // convert equipment list
    const userEquipmentList = {};
    for (const [equipmentId, equipment] of Object.entries(toSerialize.equipmentList)) {
        userEquipmentList[equipmentId] = {
            "enhancement_level": equipment.enhancementLevel,
            "level": equipment.level,
            "protection": equipment.protection,
            "stack": equipment.stack
        };
    }
    // convert player Quest Progress
    const userQuestProgress = {};
    for (const [section, progresses] of Object.entries(toSerialize.questProgress)) {
        const list = [];
        for (const progress of progresses) {
            list.push({
                "best_elapsed_time_ms": progress.bestElapsedTimeMs,
                "clear_rank": progress.clearRank,
                "finished": progress.finished,
                "host_finished": (_b = progress.hostFinished) !== null && _b !== void 0 ? _b : false,
                "high_score": (_c = progress.highScore) !== null && _c !== void 0 ? _c : 0,
                "quest_id": progress.questId,
                "unlocked": progress.unlocked
            });
        }
        userQuestProgress[section] = list;
    }
    // convert box gacha list
    const userBoxGachaList = {};
    for (const [section, list] of Object.entries(toSerialize.boxGachaList)) {
        userBoxGachaList[section] = list.map(boxGacha => {
            return {
                "box_id": boxGacha.boxId,
                "reset_times": boxGacha.resetTimes,
                "remaining_number": boxGacha.remainingNumber,
                "is_closed": boxGacha.isClosed
            };
        });
    }
    // handle tutorial
    let userTutorial = null;
    const playerData = toSerialize.player;
    const tutorialStep = playerData.tutorialStep;
    if (tutorialStep !== null
        && (0, start_tutorial_state_1.isStartTutorialActive)(tutorialStep, playerData.tutorialSkipFlag)) {
        userTutorial = {
            "viewer_id": (_d = options === null || options === void 0 ? void 0 : options.viewerId) !== null && _d !== void 0 ? _d : 0,
            "tutorial_step": tutorialStep,
            "skip_flag": playerData.tutorialSkipFlag
        };
        if (tutorialStep >= 1) {
            userTutorial["powerflip_failure"] = 0;
        }
    }
    const realTimeStamina = (0, stamina_1.computeRealTimeStamina)(playerData);
    if (realTimeStamina !== playerData.stamina) {
        (0, player_1.updatePlayerSync)({ id: playerData.id, stamina: realTimeStamina, staminaHealTime: new Date() });
        playerData.stamina = realTimeStamina;
    }
    const clientData = {
        "user_info": {
            "stamina": playerData.stamina,
            "stamina_heal_time": (0, utils_1.realToVirtual)(playerData.staminaHealTime),
            "boost_point": playerData.boostPoint,
            "boss_boost_point": playerData.bossBoostPoint,
            "transition_state": playerData.transitionState,
            "role": playerData.role,
            "name": playerData.name,
            "last_login_time": (0, date_1.clientSerializeDate)(playerData.lastLoginTime),
            "comment": playerData.comment,
            "vmoney": playerData.vmoney,
            "free_vmoney": playerData.freeVmoney,
            "rank_point": playerData.rankPoint,
            "star_crumb": playerData.starCrumb,
            "bond_token": playerData.bondToken,
            "exp_pool": playerData.expPool,
            "exp_pooled_time": (0, utils_1.getServerTime)(playerData.expPooledTime),
            "leader_character_id": playerData.leaderCharacterId != null ? (0, codeMap_1.kIdToBusinessCode)(playerData.leaderCharacterId) : 0,
            "party_slot": playerData.partySlot,
            "degree_id": (_e = playerData.degreeId) !== null && _e !== void 0 ? _e : 1,
            "birth": playerData.birth,
            "free_mana": playerData.freeMana,
            "paid_mana": playerData.paidMana,
            "enable_auto_3x": playerData.enableAuto3x
        },
        "premium_bonus_list": [],
        "expired_premium_bonus_list": null,
        "user_daily_challenge_point_list": toSerialize.dailyChallengePointList.map(dailyChallenge => {
            return {
                "id": dailyChallenge.id,
                "point": dailyChallenge.point,
                "campaign_list": dailyChallenge.campaignList.map(campaign => {
                    return {
                        "campaign_id": campaign.campaignId,
                        "additional_point": campaign.additionalPoint
                    };
                })
            };
        }),
        "bonus_index_list": null,
        "login_bonus_received_at": null,
        "user_notice_list": [],
        "user_triggered_tutorial": toSerialize.triggeredTutorial,
        "user_tutorial": userTutorial,
        "tutorial_gacha": toSerialize.player.tutorialGachaCharacterId !== null && toSerialize.player.tutorialGachaCharacterId !== undefined
            ? { character_id: toSerialize.player.tutorialGachaCharacterId }
            : null,
        "cleared_regular_mission_list": toSerialize.clearedRegularMissionList,
        "user_character_list": userCharacterList,
        "user_character_mana_node_list": (() => {
            var _a, _b;
            const awakeLevels = (_a = toSerialize.characterManaNodeAwakeLevels) !== null && _a !== void 0 ? _a : {};
            const list = {};
            for (const [charId, nodeIds] of Object.entries(toSerialize.characterManaNodeList)) {
                if (nodeIds.length > 0) {
                    const charLevels = (_b = awakeLevels[charId]) !== null && _b !== void 0 ? _b : {};
                    list[charId] = nodeIds.map(id => {
                        var _a;
                        return ({
                            multiplied_id: id,
                            awake_level: (_a = charLevels[id]) !== null && _a !== void 0 ? _a : 0
                        });
                    });
                }
            }
            return list;
        })(),
        "user_party_group_list": userPartyGroupList,
        "item_list": toSerialize.itemList,
        "user_equipment_list": userEquipmentList,
        "user_character_from_town_history": [],
        "quest_progress": userQuestProgress,
        "last_main_quest_id": null,
        "gacha_info_list": toSerialize.gachaInfoList.map(gachaInfo => {
            return {
                "gacha_id": gachaInfo.gachaId,
                "is_daily_first": gachaInfo.isDailyFirst,
                "is_account_first": gachaInfo.isAccountFirst,
                "gacha_exchange_point": gachaInfo.gachaExchangePoint
            };
        }),
        "available_asset_version": asset_1.availableAssetVersion,
        "should_prompt_takeover_registration": false,
        "has_unread_news_item": false,
        "user_option": toSerialize.userOption,
        "drawn_quest_list": toSerialize.drawnQuestList.map(drawnQuest => {
            return {
                "category_id": drawnQuest.categoryId,
                "quest_id": drawnQuest.questId,
                "odds_id": drawnQuest.oddsId
            };
        }),
        "mail_arrived": (0, mail_1.getPlayerMailCountSync)(toSerialize.player.id, true) > 0,
        "user_periodic_reward_point_list": toSerialize.periodicRewardPointList,
        "all_active_mission_list": toSerialize.allActiveMissionList,
        "cleared_collect_item_event_mission_list": (0, mission_1.getPlayerClearedCollectItemEventMissionListSync)(toSerialize.player.id),
        "box_gacha_list": userBoxGachaList,
        "gacha_campaign_list": toSerialize.gachaCampaignList.map(campaign => (0, serialize_entities_1.serializeGachaCampaign)(campaign)),
        "purchased_times_list": {
            "gs.kg.worldflipper.pakage_monthly": 0,
            "gs.kg.worldflipper.pakage_rank": 0,
            "gs.kg.worldflipper.pakage_monthly_90": 0,
            "gs.kg.worldflipper.pakage_monthly_stamina": 0,
            "gs.kg.worldflipper.pakage_monthly_kareido": 0,
            "gs.kg.worldflipper.pakage_monthly_boss": 0,
            "gs.kg.worldflipper.pakage_rank_2": 0,
            "gs.kg.worldflipper.pakage_rank_3_1": 0,
            "gs.kg.worldflipper.pakage_rank_4": 0,
            "gs.kg.worldflipper.pakage_challenge_boost": 0
        },
        "start_dash_exchange_campaign_list": toSerialize.startDashExchangeCampaignList.map(campaign => {
            return {
                "campaign_id": campaign.campaignId,
                "gacha_id": campaign.gachaId,
                "period_start_time": (0, utils_1.getServerTime)(campaign.periodStartTime),
                "period_end_time": (0, utils_1.getServerTime)(campaign.periodEndTime),
                "status": campaign.status,
                "term_index": campaign.termIndex
            };
        }),
        "multi_special_exchange_campaign_list": toSerialize.multiSpecialExchangeCampaignList.map(campaign => {
            const serialized = {
                "campaign_id": campaign.campaignId,
                "status": campaign.status
            };
            if (campaign.ticketItemId !== null && campaign.ticketItemId !== undefined) {
                serialized.ticket_item_id = campaign.ticketItemId;
            }
            return serialized;
        }),
        "associate_token": "associate_token",
        "config": {
            "summon_com_seconds": parseInt(process.env.SUMMON_COM_SECONDS || "5"),
            "attention_recruitment_interval_seconds": 15,
            "attention_recruitment_redeliver_limit": 20,
            "attention_polling_interval_seconds_normal": 10,
            "attention_polling_interval_seconds_battle": 15,
            "multi_attention_lifetime_seconds": 30,
            "contribution_score_rate_to_parasite": 0.25,
            "attention_log_interval_seconds": 600,
            "disable_finish_duration_seconds": 5,
            "disable_decline_count_seconds": 60,
            "disable_decline_count_limit": 14,
            "disable_decline_duration_seconds": 30,
            "disable_intent_disconnect_duration_seconds": 300,
            "disable_unintent_disconnect_duration_seconds": 5,
            "disable_remote_error_duration_seconds": 300,
            "attention_animation_time_seconds": 6,
            "disable_expire_count_limit": 4,
            "disable_expire_duration_seconds": 180,
            "polling_delay_normal_seconds_range_min": 1,
            "polling_delay_normal_seconds_range_max": 10,
            "polling_delay_battle_seconds_range_min": 1,
            "polling_delay_battle_seconds_range_max": 15,
            "return_attention_max_num": 3
        }
    };
    // add optional values
    // serialize rush event data
    if ((_f = options === null || options === void 0 ? void 0 : options.serializeRushEventData) !== null && _f !== void 0 ? _f : false) {
        // rush event list
        if (toSerialize.rushEventList !== undefined) {
            const userRushEventList = {};
            for (const rushEvent of toSerialize.rushEventList) {
                userRushEventList[rushEvent.eventId] = (0, serialize_entities_1.serializeRushEvent)(rushEvent);
            }
            clientData.user_rush_event_list = userRushEventList;
        }
        // cleared folder list
        clientData.user_rush_event_cleared_folder_list = toSerialize.rushEventClearedFolderList;
        // rush event played party list
        if (toSerialize.rushEventPlayedPartyList !== undefined) {
            const userRushEventPlayedPartyList = {};
            for (const [eventId, parties] of Object.entries(toSerialize.rushEventPlayedPartyList)) {
                const numericEventId = Number(eventId);
                const battleTypeBuckets = {
                    // Keep both buckets as empty maps. Leaving an unused
                    // bucket undefined emits MessagePack fixext1 (0xD4),
                    // which the legacy Android client rejects during /load.
                    [types_1.RushEventBattleType.FOLDER]: {},
                    [types_1.RushEventBattleType.ENDLESS]: {}
                };
                for (const party of parties) {
                    let bucket = battleTypeBuckets[party.battleType];
                    if (bucket === undefined) {
                        bucket = {};
                        battleTypeBuckets[party.battleType] = bucket;
                    }
                    const serializedParty = (0, rushEvent_1.serializePlayerRushEventPlayedParty)(party);
                    if ((0, mode15_optional_1.shouldUnlockMode15PlayedParties)(numericEventId)
                        || (0, mode15_optional_1.shouldUnlockMode15MultiplayerPlayedParty)(numericEventId, party.round)) {
                        clearSerializedPlayedPartyMembers(serializedParty);
                    }
                    bucket[party.round] = serializedParty;
                }
                userRushEventPlayedPartyList[eventId] = battleTypeBuckets;
            }
            clientData.user_rush_event_played_party_list = userRushEventPlayedPartyList;
        }
    }
    if (options === null || options === void 0 ? void 0 : options.activeMissionList) {
        clientData.active_mission_list = options.activeMissionList;
    }
    return clientData;
}
exports.serializePlayerData = serializePlayerData;
