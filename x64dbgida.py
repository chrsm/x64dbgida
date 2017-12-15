import idaapi, idautils, json, traceback

initialized = False
BPNORMAL = 0
BPHARDWARE = 1
UE_HARDWARE_EXECUTE = 4
UE_HARDWARE_WRITE = 5
UE_HARDWARE_READWRITE = 6
UE_HARDWARE_SIZE_1 = 7
UE_HARDWARE_SIZE_2 = 8
UE_HARDWARE_SIZE_4 = 9
UE_HARDWARE_SIZE_8 = 10


def Comments():
    lastea = 0
    lastcmt = ""
    for ea in range(MinEA(), MaxEA()):
        cmt1 = Comment(ea)
        cmt2 = RptCmt(ea)
        cmt = ""
        if cmt1:
            cmt += cmt1
        if cmt2:
            cmt += cmt2
        if (cmt):
            skip = ea == lastea + 1 and cmt == lastcmt
            lastea = ea
            lastcmt = cmt
            if not skip:
                yield (ea, cmt)


def Breakpoints():
    count = GetBptQty()
    for i in range(0, count):
        ea = GetBptEA(i)
        bpt = idaapi.bpt_t()
        if not idaapi.get_bpt(ea, bpt):
            continue
        if bpt.type & BPT_SOFT != 0:
            yield (ea, BPNORMAL, 0, Word(ea))
        else:
            bptype = BPNORMAL if bpt.type == BPT_DEFAULT else BPHARDWARE
            hwtype = {
                BPT_WRITE: UE_HARDWARE_WRITE,
                BPT_RDWR: UE_HARDWARE_READWRITE,
                BPT_EXEC: UE_HARDWARE_EXECUTE
            }[bpt.type]
            hwsize = {
                1: UE_HARDWARE_SIZE_1,
                2: UE_HARDWARE_SIZE_2,
                4: UE_HARDWARE_SIZE_4,
                8: UE_HARDWARE_SIZE_8,
            }[bpt.size]
            yield (ea, bptype, (hwtype << 4 | hwsize), 0)


def get_file_mask():
    mask = "*.dd32"
    if idaapi.get_inf_structure().is_64bit():
        mask = "*.dd64"
    return mask


def do_import():
    db = {}
    module = idaapi.get_root_filename().lower()
    base = idaapi.get_imagebase()

    file = AskFile(0, "x64dbg database|%s" % get_file_mask(),
                   "Import database")
    if not file:
        return
    print "Importing database %s" % file

    with open(file) as dbdata:
        db = json.load(dbdata)

    count = 0
    labels = db.get("labels", [])
    for label in labels:
        try:
            if label["module"] != module:
                continue
            ea = int(label["address"], 16) + base
            name = label["text"]
            MakeNameEx(ea, str(name), 0)
            count += 1
        except:
            pass
    print "%d/%d label(s) imported" % (count, len(labels))

    count = 0
    comments = db.get("comments", [])
    for comment in comments:
        try:
            if comment["module"] != module:
                continue
            ea = int(comment["address"], 16) + base
            name = comment["text"]
            MakeRptCmt(ea, str(name))
            count += 1
        except:
            pass
    print "%d/%d comment(s) imported" % (count, len(comments))

    count = 0
    breakpoints = db.get("breakpoints", [])
    for breakpoint in breakpoints:
        try:
            if breakpoint["module"] != module:
                continue
            ea = int(breakpoint["address"], 16) + base
            bptype = breakpoint["type"]
            if bptype == BPNORMAL:
                count += 1
                AddBptEx(ea, 1, BPT_DEFAULT)
            elif bptype == BPHARDWARE:
                titantype = int(breakpoint["titantype"], 16)
                hwtype = (titantype >> 4) & 0xF
                if hwtype == UE_HARDWARE_EXECUTE:
                    hwtype = BPT_EXEC
                elif hwtype == UE_HARDWARE_WRITE:
                    hwtype = BPT_WRITE
                elif hwtype == UE_HARDWARE_READWRITE:
                    hwtype = BPT_RDWR
                else:
                    continue
                hwsize = titantype & 0xF
                if hwsize == UE_HARDWARE_SIZE_1:
                    hwsize = 1
                elif hwsize == UE_HARDWARE_SIZE_2:
                    hwsize = 2
                elif hwsize == UE_HARDWARE_SIZE_4:
                    hwsize = 4
                elif hwsize == UE_HARDWARE_SIZE_8:
                    hwsize = 8
                else:
                    continue
                count += 1
                AddBptEx(ea, hwsize, hwtype)
        except:
            pass
    print "%d/%d breakpoint(s) imported" % (count, len(breakpoints))

    print "Done!"


def do_export():
    db = {}
    module = idaapi.get_root_filename().lower()
    base = idaapi.get_imagebase()

    file = AskFile(1, "x64dbg database|%s" % get_file_mask(),
                   "Export database")
    if not file:
        return
    print "Exporting database %s" % file

    db["labels"] = [{
        "text": name,
        "manual": False,
        "module": module,
        "address": "0x%X" % (ea - base)
    } for (ea, name) in Names()]
    print "%d label(s) exported" % len(db["labels"])

    db["comments"] = [{
        "text": comment.replace("{", "{{").replace("}", "}}"),
        "manual": False,
        "module": module,
        "address": "0x%X" % (ea - base)
    } for (ea, comment) in Comments()]
    print "%d comment(s) exported" % len(db["comments"])

    db["breakpoints"] = [{
        "address": "0x%X" % (ea - base),
        "enabled": True,
        "type": bptype,
        "titantype": "0x%X" % titantype,
        "oldbytes": "0x%X" % oldbytes,
        "module": module,
    } for (ea, bptype, titantype, oldbytes) in Breakpoints()]
    print "%d breakpoint(s) exported" % len(db["breakpoints"])

    with open(file, "w") as outfile:
        json.dump(db, outfile, indent=1)
    print "Done!"

class x64dbg_plugin_action_importdb(idaapi.action_handler_t):
    def __init__(self):
        idaapi.action_handler_t.__init__(self)
    
    def activate(self, ctx):
        print "Importing from x64dbg"
        try:
            do_import()
        except:
            traceback.print_exc()
            print "Error importing database..."
        return 1

    def update(self, ctx):
        return idaapi.AST_ENABLE_ALWAYS

class x64dbg_plugin_action_exportdb(idaapi.action_handler_t):
    def __init__(self):
        idaapi.action_handler_t.__init__(self)
    
    def activate(self, ctx):
        print "Exporting to x64dbg format"
        try:
            do_export()
        except:
            traceback.print_exc()
            print "Error exporting database..."
        return 1

    def update(self, ctx):
        return idaapi.AST_ENABLE_ALWAYS


class x64dbg_plugin_t(idaapi.plugin_t):
    comment = "Official x64dbg plugin for IDA Pro"
    version = "v1.0"
    website = "https://github.com/x64dbg/x64dbgida"
    help = ""
    wanted_name = "x64dbgida"
    wanted_hotkey = ""
    flags = idaapi.PLUGIN_KEEP

    def init(self):
        global initialized

        if initialized == False:
            initialized = True
            '''menu = idaapi.add_menu_item("Edit/x64dbgida/", "About", "", 0,
                                        self.about, None)
            if menu is not None:
                idaapi.add_menu_item("Edit/x64dbgida/", "Export database", "",
                                     0, self.exportdb, None)
                idaapi.add_menu_item("Edit/x64dbgida/",
                                     "Import (uncompressed) database", "", 0,
                                     self.importdb, None)
            elif idaapi.IDA_SDK_VERSION < 680:
                idaapi.add_menu_item("File/Produce file/",
                                     "Export x64dbg database", "", 0,
                                     self.exportdb, None)
                idaapi.add_menu_item("File/Load file/",
                                     "Import x64dbg database", "", 0,
                                     self.importdb, None)
            '''
            act_export = idaapi.action_desc_t(
                'x64dbg:export_db',
                'Export IDA -> x64dbg',
                x64dbg_plugin_action_exportdb(),
                '',
                'Export IDA -> x64dbg',
            )

            act_import = idaapi.action_desc_t(
                'x64dbg:import_db',
                'Import x64dbg -> IDA',
                x64dbg_plugin_action_importdb(),
                '',
                'Import x64dbg -> IDA',
            )

            idaapi.register_action(act_export)
            idaapi.register_action(act_import)

            idaapi.attach_action_to_menu(
                'Edit/x64dbg/Export DB',
                'x64dbg:export_db',
                idaapi.SETMENU_APP,
            )

            idaapi.attach_action_to_menu(
                'Edit/x64dbg/Import DB',
                'x64dbg:import_db',
                idaapi.SETMENU_APP,
            )

        return idaapi.PLUGIN_OK

    def run(self, arg):
        self.about()

    def term(self):
        return

    def about(self):
        print self.wanted_name + " " + self.version
        print self.comment
        print self.website


def PLUGIN_ENTRY():
    return x64dbg_plugin_t()
