package cn.mod {
    /** Visual selection only; damage kind and ownership stay with native rules. */
    public final class InahoAbilityVisuals {
        private static const ROOT:String = "battle/effect/ability_damage/inaho_midautumn_wip/";
        private static const INAHO_MARKER:String = "cnmod_inaho_midautumn";

        public static function preload(source:Object, builder:Object):void {
            if (needsInahoPreload(source)) {
                builder.addAnimationLayout(ROOT + "moonlight_launch");
                builder.addAnimationLayout(ROOT + "moonlight_shot_gold_jade");
                builder.addAnimationLayout(ROOT + "moonlight_hit");
                builder.addAnimationLayout("battle/effect/skill_unique/inaho_midautumn_wip/midautumn_native/effect");
            }
            builder.addAnimationLayout("battle/common/layer1/total_ability_damage_effect");
            builder.addAnimationLayout("battle/common/layer1/total_powerflip_damage_effect");
        }

        public static function shot(ability:Object, element:int):String {
            if (isInaho(ability)) return ROOT + "moonlight_shot_gold_jade";
            switch (element) {
                case 0: return "battle/effect/ability_damage/ability_damage_red/ability_damage_shot_red";
                case 1: return "battle/effect/ability_damage/ability_damage_blue/ability_damage_shot_blue";
                case 2: return "battle/effect/ability_damage/ability_damage_yellow/ability_damage_shot_yellow";
                case 3: return "battle/effect/ability_damage/ability_damage_green/ability_damage_shot_green";
                case 4: return "battle/effect/ability_damage/ability_damage_white/ability_damage_shot_white";
                case 5: return "battle/effect/ability_damage/ability_damage_black/ability_damage_shot_black";
                default: return "battle/effect/ability_damage/ability_damage_white/ability_damage_shot_white";
            }
        }

        public static function hit(ability:Object, fallback:String):String {
            return isInaho(ability) ? ROOT + "moonlight_hit" : fallback;
        }

        private static function needsInahoPreload(source:Object):Boolean {
            try {
                var content:Object = source.content;
                if (content == null || int(content.index) != 4) return false;
                var instant:Object = content.params[1];
                if (instant == null || int(instant.index) != 19) return false;
                var path:String = String(instant.params[1]);
                return path.indexOf(INAHO_MARKER) >= 0;
            } catch (error:Error) {
                return false;
            }
        }

        private static function isInaho(ability:Object):Boolean {
            try {
                var source:Object = ability.member.getCharacter();
                var code:String = String(source.mainCharacterStringId);
                var pixel:String = String(source.pixelArtAnimationPath);
                return code == "cnmod_inaho_midautumn" ||
                    pixel.indexOf("cnmod_inaho_midautumn") >= 0 ||
                    pixel.indexOf("inaho_midautumn") >= 0;
            } catch (error:Error) {
                return false;
            }
        }
    }
}
