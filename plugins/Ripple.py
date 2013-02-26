import psycopg2
import re
from sets import Set
from ripplelogin import dbname, dbuser, dbpass

class RipplePlugin:
    def __init__(self, client):
        self.conn = psycopg2.connect(database = dbname, user = dbuser, password = dbpass)
        self.cur = self.conn.cursor()
        self.cur.execute("SET timezone = 'UTC';")
        self.conn.commit()
        client.register_dispatch(self.chat_received, 0x03)
    
    def chat_received(self, packet):
        msg = packet.data['text'].lower()
        match = re.search('^([A-Za-z0-9]+): ([A-Za-z0-9]+)(.*)', msg)
        if match:
            sender = match.group(0)
            command = match.group(1)
            remaining = match.group(2)
            if command == 'trust':
                arg_match = re.search('^ ([A-Za-z0-9]+) ([0-9]+(?:\.[0-9]{1,2})?)d', remaining)
                if arg_match:
                    self.send_pm(sender, "Matched trust arguments")
                else:
                    self.send_pm(sender, "Usage: trust <person> <amount>d")
            else:
                self.send_pm(sender, "Command not understood: %s" % (command))
    
    def send_pm(self, user, message):
        self.client.push(Packet(ident=0x03, data={'text':"/msg %s %s" % (user, message)}))
    
    def add_trust(trustor, trustee, amount, currency):
        self.cur.execute("""SELECT 1 FROM trusts WHERE trustor = %s AND trustee = %s AND currency = %s""", (currency, expand_set))
        if row = self.cur.fetchone():
            self.cur.execute("""UPDATE trusts SET amount = amount + %s WHERE trustor = %s AND trustee = %s AND currency = %s""", (amount, trustor, trustee, currency))
        else:
            self.cur.execute("""INSERT INTO trusts (trustor, trustee, amount, currency) VALUES (%s, %s, %s, %s)""", (trustor, trustee, amount, currency))
        self.cur.commit()
    
    def reduce_trust(trustor, trustee, amount, currency):
        self.cur.execute("""SELECT amount FROM trusts WHERE trustor = %s AND trustee = %s AND currency = %s""", (currency, expand_set))
        if row = self.cur.fetchone():
            if row[0] >= amount:
                self.cur.commit()
                self.cur.execute("""UPDATE trusts SET amount = amount - %s WHERE trustor = %s AND trustee = %s AND currency = %s""", (amount, trustor, trustee, currency))
                self.send_pm(sender, "Reduced trust in %s by %f" % (recipient, amount))
            else:
                self.delete_trust(trustor, trustee, currency)
        else:
            self.delete_trust(trustor, trustee, currency)
    
    def delete_trust(trustor, trustee, currency):
        self.cur.execute("""DELETE FROM trusts WHERE trustor = %s AND trustee = %s AND currency = %s""", (trustor, trustee, currency))
        self.cur.commit()
        self.send_pm(sender, "Revoked trust in %s" % (recipient))
    
    def send_payment(sender, recipient, amount, currency):
        paths = find_paths(sender, recipient, amount, currency)
        total_amount = 0
        for pair in paths:
            total_amount += pair[1]
        if total_amount == amount:
            self.transact_paths(paths)
            self.send_pm(sender, "Sent %f to %s" % (amount, recipient))
        else:
            self.send_pm(sender, "Could not send payment of %f to %s, maximum is %f" % (amount, recipient, total_amount))
    
    def reject_owed(trustee, trustor, amount, currency):
        # TODO: Reject a debt owed by someone who trusts you
        # Creates permanent record and destroys trust link
    
    def find_paths(sender, recipient, amount, currency):
        expand_set = Set([sender])
        edge_paths = [[sender]]
        paths = []
        while expand_set:
            available_links = Set()
            # Follow paths of repaying debt
            self.cur.execute("""SELECT debt_from, debt_to FROM debts WHERE currency = %s AND debt_to IN (%s)""", (currency, expand_set))
            while row = self.cur.fetchone():
                available_links.add(row)
                
            # Follow paths of trusted debt acquisition
            self.cur.execute("""SELECT trustee, trustor FROM trusts WHERE currency = %s AND trustee IN (%s)""", (currency, expand_set))
            while row = self.cur.fetchone():
                available_links.add(row)
            
            next_paths = []
            next_nodes = Set()
            for path in edge_paths:
                for link in available_links:
                    if link[0] == path[-1]:
                        if link[1] == recipient:
                            # Reached the recipient - measure capacity
                            bottleneck = self.find_bottleneck(path, currency, paths)
                            if bottleneck == None or bottleneck >= amount:
                                # We can send all remaining money along this path
                                paths.append(path, amount)
                                return paths
                            else:
                                # We can only send part along this path
                                paths.append(path, bottleneck)
                                amount -= bottleneck
                        elsif link[1] not in path:
                            new_path = path[:]
                            new_path.append(link[1])
                            next_paths.append(new_path)
                            next_nodes.add(link[1])
            expand_set = next_nodes
        return paths
    
    def find_bottleneck(path, currency, prior_paths):
        # TODO: find how much we can send along a path
        limit = None
        from_account = path[0]
        for to_account in path[1:]:
            link_limit = self.find_max_trusted_transfer(from_account, to_account, currency)
            for pair in prior_paths:
                path = pair[0]
                prior_amount = pair[1]
                if from_account in path and path[path.index(from_account)+1] == to_account:
                    # Prior path has this link in it
                    link_limit = link_limit - prior_amount
            if link_limit <= 0:
                return 0
            if limit == None or link_limit < limit:
                limit = link_limit
            from_account = to_account
        return limit
    
    def find_max_trusted_transfer(from_account, to_account, currency):
        trusted_amount = 0
        self.cur.execute("""SELECT amount FROM trusts WHERE currency = %s AND trustor = %s AND trustee = %s""", (currency, to_account, from_account))
        while row = self.cur.fetchone():
            trusted_amount += row[0]
        
        already_used = 0
        self.cur.execute("""SELECT amount FROM debts WHERE debt_from = %s AND debt_to = %s AND currency = %s""", (from_account, to_account, currency))
        while row = self.cur.fetchone():
            already_used += row[0]
        
        back_owed = 0
        self.cur.execute("""SELECT amount FROM debts WHERE debt_from = %s AND debt_to = %s AND currency = %s""", (to_account, from_account, currency))
        while row = self.cur.fetchone():
            back_owed += row[0]
        
        return max(0, trusted_amount + back_owed - already_used)
    
    def transact_paths(paths):
        # TODO: atomically send money along these paths
        pass