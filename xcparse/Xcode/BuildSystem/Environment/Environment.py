import os
from .EnvVarCondition import *
from .EnvVariable import *
from ...XCConfig.xcconfig import *
from ....Helpers import logging_helper
from ....Helpers import xcrun_helper
from ....Helpers import plist_helper

class Environment(object):
    
    def __init__(self):
        self.settings = {};
        # load default environment types
        self.levels = [{}, {}, {}, {}]
        self.levels_dict = {
            'default': self.levels[0],
            'project': self.levels[1],
            'config': self.levels[2],
            'target': self.levels[3],
        };
        
    def loadDefaults(self):
        # load spec com.apple.buildsettings.standard
        # load spec com.apple.build-system.core
        
        # setting up default environment
        self.applyConfig(xcconfig(xcconfig.pathForBuiltinConfigWithName('defaults.xcconfig')));
        self.applyConfig(xcconfig(xcconfig.pathForBuiltinConfigWithName('runtime.xcconfig')));
        self.setValueForKey('DEVELOPER_DIR', xcrun_helper.resolve_developer_path(), {});
        platform_path = xcrun_helper.make_xcrun_with_args(('--show-sdk-platform-path', '--sdk', self.valueForKey('SDKROOT')));
        self.setValueForKey('PLATFORM_DIR', platform_path, {});
        sdk_path = xcrun_helper.resolve_sdk_path(self.valueForKey('SDKROOT'));
        self.setValueForKey('PLATFORM_DEVELOPER_SDK_DIR', os.path.dirname(sdk_path), {});
        
        # load these from the platform info.plist
        platform_info_path = os.path.join(platform_path, 'Info.plist');
        platform_info_plist = plist_helper.LoadPlistFromDataAtPath(platform_info_path);
        self.setValueForKey('PLATFORM_NAME', platform_info_plist['Name'], {});
        self.setValueForKey('PLATFORM_PREFERRED_ARCH', '', {});
        self.setValueForKey('PLATFORM_PRODUCT_BUILD_VERSION', '', {});
        # load defaults from platform
        for platform_default_setting_key in platform_info_plist['DefaultProperties'].keys():
            value = platform_info_plist['DefaultProperties'][platform_default_setting_key]
            self.setValueForKey(platform_default_setting_key, value, {});
        # load overrides
        if 'OverrideProperties' in platform_info_plist.keys():
            for platform_override_setting_key in platform_info_plist['OverrideProperties'].keys():
                value = platform_info_plist['OverrideProperties'][platform_override_setting_key];
                self.setValueForKey(platform_override_setting_key, value, {});
        
        # load these from sdk info.plist
        sdk_info_path = os.path.join(sdk_path, 'SDKSettings.plist');
        sdk_info_plist = plist_helper.LoadPlistFromDataAtPath(sdk_info_path);
        self.setValueForKey('SDKROOT', sdk_info_plist['CanonicalName'], {});
        for sdk_default_setting_key in sdk_info_plist['DefaultProperties'].keys():
            value = sdk_info_plist['DefaultProperties'][sdk_default_setting_key];
            self.setValueForKey(sdk_default_setting_key, value, {});
        
        self.setValueForKey('CLANG_ANALYZER_MALLOC', 'YES', {});
    
    def addOptions(self, options_array):
        for item in options_array:
            if item['Name'] in self.settings.keys():
                self.settings[item['Name']].mergeDefinition(item);
            else:
                self.settings[item['Name']] = EnvVariable(item);
    
    def applyConfig(self, config_obj):
        for line in config_obj.lines:
            if line.type == 'KV':
                self.setValueForKey(line.key(), line.value(None), line.conditions());
            if line.type == 'COMMENT':
                # ignore this type of line
                continue;
            if line.type == 'INCLUDE':
                base_path = os.path.dirname(config_obj.path);
                path = line.includePath(base_path);
                self.applyConfig(xcconfig(path));
    
    def isEnvironmentVariable(self, key_string):
        is_envar = False;
        find_sub = key_string.find('$');
        if find_sub != -1:
            offset = find_sub + 1;
            next_char = key_string[offset];
            if next_char == '(' or next_char == '{':
                is_envar = True;
        return is_envar;
    
    def __extractKey(self, key_string):
        return key_string[2:-1];

    def __findAndSubKey(self, key_string):
        iter = re.finditer(r'\$[\(|\{]\w*[\)|\}]', key_string);
        new_string = '';
        offset = 0
        for item in iter:
            key = self.__extractKey(item.group());
            if key in self.settings.keys():
                value = self.valueForKey(key);
                new_string += key_string[offset:item.start()] + value;
                offset = item.end();
            else:
                if key == 'inherited':
                    logging_helper.getLogger().info('[Environment]: get higher level setting');
                else:
                    logging_helper.getLogger().error('[Environment]: Error in parsing key "%s"' % key_string);
        new_string += key_string[offset:];
        return new_string;
    
    def parseKey(self, key_string):
        done_key = False;
        while done_key == False:
            temp = self.__findAndSubKey(key_string);
            if temp == key_string:
                done_key = True;
            key_string = temp;
        return (True, key_string, len(key_string));
    
    def setValueForKey(self, key, value, condition_dict):
        if key not in self.settings.keys():
            option_dict = {};
            option_dict['Name'] = key;
            if len(condition_dict.keys()) == 0:
                option_dict['DefaultValue'] = value;
            else:
                option_dict['DefaultValue'] = '';
            self.settings[key] = EnvVariable(option_dict);
        if key in self.settings.keys():
            result = self.settings[key];
            if result != None:
                result.addConditionalValue(EnvVarCondition(condition_dict, value));
        
    
    def valueForKey(self, key):
        value = None;
        if key in self.settings.keys():
            result = self.settings[key];
            if result != None:
                value = result.value(self);
        if value != None:
            test_value = self.parseKey(value);
            if test_value[0] == True:
                value = test_value[1];
        return value;
    
    def getBuildComponents(self):
        components_lookup_dict = {
            'build': 'headers build',
            'analyze': 'headers build',
            'copysrc': 'source',
            'copyhdrs': 'headers',
            'copyrsrcs': 'resources',
            'install': 'headers build',
            'installdebugonly': 'build',
            'installprofileonly': 'build',
            'installdebugprofileonly': 'build',
            'installhdrs': 'headers',
            'installsrc': 'source',
            'installrsrcs': 'resources',
        };
        additional_settings_lookup_dict = {
            'installdebugonly': [('DEPLOYMENT_LOCATION', 'YES'), ('DEPLOYMENT_POSTPROCESSING', 'YES'), ('BUILD_VARIANTS', 'debug')],
            'installprofileonly': [('DEPLOYMENT_LOCATION', 'YES'), ('DEPLOYMENT_POSTPROCESSING', 'YES'), ('BUILD_VARIANTS', 'profile')],
            'installdebugprofileonly': [('DEPLOYMENT_LOCATION', 'YES'), ('DEPLOYMENT_POSTPROCESSING', 'YES'), ('BUILD_VARIANTS', 'profile debug')],
            'installhdrs': [('DEPLOYMENT_LOCATION', 'YES'), ('DEPLOYMENT_POSTPROCESSING', 'YES')],
            'installsrc': [('DEPLOYMENT_LOCATION', 'YES'), ('DEPLOYMENT_POSTPROCESSING', 'YES')],
            'installrsrcs': [('DEPLOYMENT_LOCATION', 'YES'), ('DEPLOYMENT_POSTPROCESSING', 'YES')],
        };
        action_value = self.valueForKey('ACTION');
        if action_value in additional_settings_lookup_dict.keys():
            values = additional_settings_lookup_dict[action_value];
            for value in values:
                self.setValueForKey(value[0], value[1], {});
        if action_value in components_lookup_dict.keys():
            return components_lookup_dict[action_value];
        else:
            logging_helper.getLogger().warn('[Environment]: Unable to find ACTION');
            return '';
    
    
    def exportValues(self):
        export_list = [];
        for key in sorted(self.settings.keys()):
            # this need to change to parse out the resulting values completely
            value = self.valueForKey(key);
            result = self.parseKey(value);
            if result[0] == True:
                value = result[1];
            export_item = 'export '+key+'=';
            if self.settings[key].type == 'String':
                export_item += '"'+value+'"';
            else:
                export_item += value;
            export_list.append(export_item);
        return export_list;