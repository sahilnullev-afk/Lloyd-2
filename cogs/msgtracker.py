import discord
from discord.ext import commands
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

# --- INTERACTIVE DROPDOWN MENU ---
class MsgCommandSelect(discord.ui.Select):
    def __init__(self, bot, target_user=None):
        self.bot = bot
        self.target_user = target_user
        options = [
            discord.SelectOption(label="24h Top Members", value="msg_top", description="Pichle 24 hours ke top 20 members", emoji="🏆"),
            discord.SelectOption(label="Weekly Top Members", value="msgw_top", description="Pichle 7 days ke top members", emoji="⭐"),
            discord.SelectOption(label="User 24h Stats", value="msg_user", description="Selected user ki 24h channel breakdown", emoji="📊"),
            discord.SelectOption(label="User Weekly Combined", value="msgw_user", description="User ke 24h + 7 Days total stats", emoji="📈"),
            discord.SelectOption(label="Message Help Guide", value="msg_help", description="All message tracking commands info", emoji="❓")
        ]
        super().__init__(placeholder="⚡ Select Command to Execute...", min_values=1, max_values=1, options=options, row=1)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cog = self.bot.get_cog("MsgTracker")
        if not cog:
            await interaction.followup.send("❌ Error: MsgTracker Cog active nahi hai!", ephemeral=True)
            return

        user = self.target_user or interaction.user
        val = self.values[0]

        if val == "msg_top":
            embed, view = await cog.get_msg_top_data(interaction.guild, interaction.user)
            await interaction.followup.send(embed=embed, view=view)
        elif val == "msgw_top":
            embed, view = await cog.get_msgw_top_data(interaction.guild, interaction.user)
            await interaction.followup.send(embed=embed, view=view)
        elif val == "msg_user":
            embed, view = await cog.get_msg_user_data(interaction.guild, user)
            await interaction.followup.send(embed=embed, view=view)
        elif val == "msgw_user":
            embed, view = await cog.get_msgw_user_data(interaction.guild, user)
            await interaction.followup.send(embed=embed, view=view)
        elif val == "msg_help":
            embed, view = await cog.get_msg_help_data(interaction.user)
            await interaction.followup.send(embed=embed, view=view)


# --- PAGINATION & DROPDOWN COMBINED VIEW ---
class MsgTopPaginationView(discord.ui.View):
    def __init__(self, bot, author, rows, guild):
        super().__init__(timeout=180)
        self.bot = bot
        self.author = author
        self.rows = rows
        self.guild = guild
        self.current_page = 1
        
        self.add_item(MsgCommandSelect(bot))
        self.update_buttons()

    def update_buttons(self):
        self.prev_btn.disabled = (self.current_page == 1)
        self.next_btn.disabled = (self.current_page == 2 or len(self.rows) <= 10)

    def create_embed(self):
        embed = discord.Embed(
            title="TOP 10 CHAT MEMBERS",
            color=discord.Color.red()
        )

        if self.current_page == 1:
            page_rows = self.rows[:10]
            start_rank = 1
        else:
            page_rows = self.rows[10:20]
            start_rank = 11

        lines = []
        for idx, item in enumerate(page_rows, start_rank):
            user_id = item["_id"]
            count = item["msg_count"]
            member = self.guild.get_member(user_id)
            name = member.display_name if member else f"User `{user_id}`"
            lines.append(f"**{idx}.** `{name[:15]}`: **{count}** msgs")

        page_text = "\n".join(lines) if lines else "No Data"
        embed.description = page_text
        embed.set_footer(text=f"Page {self.current_page}/2 • Requested by {self.author.display_name}", icon_url=self.author.display_avatar.url)

        return embed

    @discord.ui.button(label="◀️ Prev", style=discord.ButtonStyle.primary, row=0)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author.id:
            return await interaction.response.send_message("❌ Yeh action aapke liye nahi hai!", ephemeral=True)
        
        self.current_page = 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.primary, row=0)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author.id:
            return await interaction.response.send_message("❌ Yeh action aapke liye nahi hai!", ephemeral=True)
        
        self.current_page = 2
        self.update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)


class MsgDropdownView(discord.ui.View):
    def __init__(self, bot, author, target_user=None):
        super().__init__(timeout=180)
        self.add_item(MsgCommandSelect(bot, target_user))


# --- MAIN COG CLASS ---
IST = ZoneInfo("Asia/Kolkata")


class MsgTracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @property
    def msg_col(self):
        if getattr(self.bot, "async_db", None) is not None:
            return self.bot.async_db["message_logs"]
        return None

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild or self.msg_col is None:
            return

        try:
            now = datetime.now(timezone.utc)
            await self.msg_col.insert_one({
                "guild_id": message.guild.id,
                "channel_id": message.channel.id,
                "user_id": message.author.id,
                "timestamp": now,
                "date_ist": now.astimezone(IST).date().isoformat(),
            })
        except Exception as e:
            print(f"[MsgTracker MongoDB Error] {e}")

    def day_bounds_ist(self, days_ago=0):
        local_start = datetime.now(IST).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_ago)
        local_end = local_start + timedelta(days=1)
        return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc)

    def day_start_ist(self):
        return self.day_bounds_ist(0)[0]

    def daily_match(self, guild_id, user_id=None):
        start, end = self.day_bounds_ist(0)
        base = {"guild_id": guild_id}
        if user_id is not None:
            base["user_id"] = user_id
        return {"$and": [base, {"$or": [
            {"date_ist": datetime.now(IST).date().isoformat()},
            {"timestamp": {"$gte": start, "$lt": end}},
        ]}]}

    async def get_msg_top_data(self, guild, author):
        if self.msg_col is None:
            embed = discord.Embed(title="Error", description="❌ MongoDB connection error! Check MONGO_URI in Render.", color=discord.Color.red())
            return embed, MsgDropdownView(self.bot, author)
        try:
            pipeline = [
                {"$match": self.daily_match(guild.id)},
                {"$group": {"_id": "$user_id", "msg_count": {"$sum": 1}}},
                {"$sort": {"msg_count": -1}},
                {"$limit": 20}
            ]
            rows = await self.msg_col.aggregate(pipeline).to_list(length=20)
            if not rows:
                embed = discord.Embed(
                    title="TOP 10 CHAT MEMBERS",
                    description="⚠️ Aaj 12:00 AM IST ke baad koi message data available nahi hai.",
                    color=discord.Color.red()
                )
                return embed, MsgDropdownView(self.bot, author)
            view = MsgTopPaginationView(self.bot, author, rows, guild)
            return view.create_embed(), view
        except Exception as e:
            print(f"[MsgTracker MongoDB Error] get_msg_top_data: {type(e).__name__}: {e}")
            embed = discord.Embed(title="Error", description="❌ MongoDB query failed. Render logs me `[MsgTracker MongoDB Error]` check karein.", color=discord.Color.red())
            return embed, MsgDropdownView(self.bot, author)

    async def get_msgw_top_data(self, guild, author):
        if self.msg_col is None:
            embed = discord.Embed(title="Error", description="❌ MongoDB connection error! Check MONGO_URI in Render.", color=discord.Color.red())
            return embed, MsgDropdownView(self.bot, author)
        try:
            start = self.day_start_ist() - timedelta(days=6)
            pipeline = [
                {"$match": {"guild_id": guild.id, "timestamp": {"$gte": start}}},
                {"$group": {"_id": "$user_id", "msg_count": {"$sum": 1}}},
                {"$sort": {"msg_count": -1}},
                {"$limit": 10}
            ]
            rows = await self.msg_col.aggregate(pipeline).to_list(length=10)
            embed = discord.Embed(title="⭐ Top Members Leaderboard (Last 7 Days)", color=discord.Color.red())
            if not rows:
                embed.description = "⚠️ Last 7 days me koi message record nahi mila."
            else:
                embed.description = "\n".join(
                    f"**#{i}** {guild.get_member(x['_id']).mention if guild.get_member(x['_id']) else f'User `{x["_id"]}`'} — **{x["msg_count"]}** Messages"
                    for i, x in enumerate(rows, 1)
                )
            embed.set_footer(text=f"Requested by {author.display_name}", icon_url=author.display_avatar.url)
            return embed, MsgDropdownView(self.bot, author)
        except Exception as e:
            print(f"[MsgTracker MongoDB Error] get_msgw_top_data: {type(e).__name__}: {e}")
            embed = discord.Embed(title="Error", description="❌ MongoDB query failed. Render logs me `[MsgTracker MongoDB Error]` check karein.", color=discord.Color.red())
            return embed, MsgDropdownView(self.bot, author)

    async def get_msg_user_data(self, guild, target_user):
        if self.msg_col is None:
            embed = discord.Embed(title="Error", description="❌ MongoDB connection error! Check MONGO_URI in Render.", color=discord.Color.red())
            return embed, MsgDropdownView(self.bot, target_user, target_user)
        try:
            pipeline = [
                {"$match": self.daily_match(guild.id, target_user.id)},
                {"$group": {"_id": "$channel_id", "msg_count": {"$sum": 1}}},
                {"$sort": {"msg_count": -1}}
            ]
            rows = await self.msg_col.aggregate(pipeline).to_list(length=None)
            embed = discord.Embed(title=f"📊 Today's Message Breakdown — {target_user.display_name}", color=discord.Color.red())
            embed.set_thumbnail(url=target_user.display_avatar.url)
            total = sum(item["msg_count"] for item in rows)
            if not rows:
                embed.description = "⚠️ Aaj 12:00 AM IST ke baad is user ne ek bhi message nahi bheja hai."
            else:
                embed.description = "**Channel Activity List:**\n" + "\n".join(
                    f"• {guild.get_channel(item['_id']).mention if guild.get_channel(item['_id']) else '#deleted-channel'}: **{item['msg_count']}** msgs"
                    for item in rows
                )
            embed.add_field(name="📈 Today's Messages", value=f"**{total}** Messages", inline=False)
            embed.set_footer(text=f"User ID: {target_user.id}")
            return embed, MsgDropdownView(self.bot, target_user, target_user)
        except Exception as e:
            print(f"[MsgTracker MongoDB Error] get_msg_user_data: {type(e).__name__}: {e}")
            embed = discord.Embed(title="Error", description="❌ MongoDB query failed. Render logs me `[MsgTracker MongoDB Error]` check karein.", color=discord.Color.red())
            return embed, MsgDropdownView(self.bot, target_user, target_user)

    async def get_msgw_user_data(self, guild, target_user):
        if self.msg_col is None:
            embed = discord.Embed(title="Error", description="❌ MongoDB connection error! Check MONGO_URI in Render.", color=discord.Color.red())
            return embed, MsgDropdownView(self.bot, target_user, target_user)
        try:
            start_day = self.day_start_ist()
            start_7d = start_day - timedelta(days=6)
            count_day = await self.msg_col.count_documents({
                "guild_id": guild.id, "user_id": target_user.id,
                "$or": [{"date_ist": datetime.now(IST).date().isoformat()},
                        {"timestamp": {"$gte": start_day, "$lt": start_day + timedelta(days=1)}}]
            })
            count_7d = await self.msg_col.count_documents({
                "guild_id": guild.id, "user_id": target_user.id,
                "timestamp": {"$gte": start_7d}
            })
            embed = discord.Embed(title=f"📈 Overview Stats — {target_user.display_name}", color=discord.Color.red())
            embed.set_thumbnail(url=target_user.display_avatar.url)
            embed.add_field(name="🇮🇳 Today", value=f"**{count_day}** Messages", inline=True)
            embed.add_field(name="📅 Last 7 Days", value=f"**{count_7d}** Messages", inline=True)
            embed.set_footer(text=f"User ID: {target_user.id}")
            return embed, MsgDropdownView(self.bot, target_user, target_user)
        except Exception as e:
            print(f"[MsgTracker MongoDB Error] get_msgw_user_data: {type(e).__name__}: {e}")
            embed = discord.Embed(title="Error", description="❌ MongoDB query failed. Render logs me `[MsgTracker MongoDB Error]` check karein.", color=discord.Color.red())
            return embed, MsgDropdownView(self.bot, target_user, target_user)

    async def get_msg_help_data(self, author):
        embed = discord.Embed(
            title="❓ Message Tracking System — Commands Guide",
            description="Aap neeche likhi commands type karke ya dropdown menu se select karke use kar sakte hain:",
            color=discord.Color.red()
        )
        embed.add_field(name="🔹 !msg top", value="Aaj 12:00 AM IST se Top 20 Active Members ki list (Page 1: 1-10 | Page 2: 11-20).", inline=False)
        embed.add_field(name="🔹 !msg @user", value="Targeted member ki 24h ki Channel-wise breakdown & Total Messages.", inline=False)
        embed.add_field(name="🔹 !msgw top", value="Pichle 7 Days (Weekly) ke Top Message senders ki Leaderboard.", inline=False)
        embed.add_field(name="🔹 !msgw @user", value="Member ke 24h aur 7 Days (Weekly) ka overall summary calculation.", inline=False)
        embed.add_field(name="🔹 !msg help", value="Ye Help Menu UI display karega.", inline=False)
        
        embed.set_footer(text="⚡ Select commands from the dropdown menu below!")
        return embed, MsgDropdownView(self.bot, author)

    @commands.hybrid_group(name="msg", invoke_without_command=True)
    async def msg_group(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        embed, view = await self.get_msg_user_data(ctx.guild, target)
        await ctx.send(embed=embed, view=view)

    @msg_group.command(name="top")
    async def msg_top(self, ctx):
        embed, view = await self.get_msg_top_data(ctx.guild, ctx.author)
        await ctx.send(embed=embed, view=view)

    @msg_group.command(name="help")
    async def msg_help_cmd(self, ctx):
        embed, view = await self.get_msg_help_data(ctx.author)
        await ctx.send(embed=embed, view=view)

    @commands.hybrid_group(name="msgw", invoke_without_command=True)
    async def msgw_group(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        embed, view = await self.get_msgw_user_data(ctx.guild, target)
        await ctx.send(embed=embed, view=view)

    @msgw_group.command(name="top")
    async def msgw_top(self, ctx):
        embed, view = await self.get_msgw_top_data(ctx.guild, ctx.author)
        await ctx.send(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(MsgTracker(bot))
                                                      
