import { useEffect, useMemo, useState } from 'react';
import DatePicker from 'react-datepicker';
import 'react-datepicker/dist/react-datepicker.css';
import api from '../services/api';
import { useTelegram } from '../hooks/useTelegram';
import EditModal from '../components/Modals/EditModal';

const FILTERS = [
  { key: 'all', label: '🔘 Все', activeClass: 'bg-blue-500 text-white', idleClass: 'bg-gray-200 text-gray-700' },
  { key: 'expense', label: '⬇️ Расходы', activeClass: 'bg-red-500 text-white', idleClass: 'bg-gray-200 text-gray-700' },
  { key: 'income', label: '⬆️ Приходы', activeClass: 'bg-green-500 text-white', idleClass: 'bg-gray-200 text-gray-700' },
  { key: 'transfer', label: '🔄 Переводы', activeClass: 'bg-yellow-500 text-white', idleClass: 'bg-gray-200 text-gray-700' },
  { key: 'incasation', label: '💼 Инкасация', activeClass: 'bg-purple-500 text-white', idleClass: 'bg-gray-200 text-gray-700' },
];

export default function Timeline() {
  const [operations, setOperations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [editItem, setEditItem] = useState(null);
  const { showAlert } = useTelegram();

  // Фильтрация по периодам
  const generateMonthOptions = () => {
    const months = [];
    const now = new Date();
    
    for (let i = 0; i < 12; i++) {
      const date = new Date(now.getFullYear(), now.getMonth() - i, 1);
      const year = date.getFullYear();
      const month = String(date.getMonth() + 1).padStart(2, '0');
      const value = `${year}-${month}`;
      
      const monthNames = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 
                          'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];
      const label = `${monthNames[date.getMonth()]} ${year}`;
      
      months.push({ value, label });
    }
    
    return months;
  };

  const monthOptions = generateMonthOptions();
  const currentMonth = monthOptions[0].value;
  
  const [period, setPeriod] = useState('month');
  const [selectedMonth, setSelectedMonth] = useState(currentMonth);
  const [customStart, setCustomStart] = useState(null);
  const [customEnd, setCustomEnd] = useState(null);

  useEffect(() => {
    loadOperations();
  }, [period, selectedMonth, customStart, customEnd]);

  const loadOperations = async () => {
    setLoading(true);
    try {
      let params = { limit: 200 };
      
      if (period === 'month') {
        const [year, month] = selectedMonth.split('-');
        const startDate = new Date(parseInt(year), parseInt(month) - 1, 1);
        const endDate = new Date(parseInt(year), parseInt(month), 0);
        
        params.start_date = startDate.toISOString().split('T')[0];
        params.end_date = endDate.toISOString().split('T')[0];
      } else if (period === 'custom' && customStart && customEnd) {
        params.start_date = customStart.toISOString().split('T')[0];
        params.end_date = customEnd.toISOString().split('T')[0];
      } else if (period !== 'custom' && period !== 'month') {
        // Для 7 и 30 дней вычисляем диапазон
        const endDate = new Date();
        const startDate = new Date();
        startDate.setDate(startDate.getDate() - parseInt(period));
        
        params.start_date = startDate.toISOString().split('T')[0];
        params.end_date = endDate.toISOString().split('T')[0];
      }
      
      const data = await api.getTimeline(params);
      setOperations(data || []);
    } catch (error) {
      console.error('Ошибка загрузки timeline:', error);
      showAlert?.('❌ Не удалось загрузить операции');
    } finally {
      setLoading(false);
    }
  };

  const filteredOperations = useMemo(() => {
    if (filter === 'all') {
      return operations;
    }
    return operations.filter((item) => item.type === filter);
  }, [operations, filter]);

  // Группируем операции по дням
  const groupedByDate = useMemo(() => {
    const groups = {};
    filteredOperations.forEach((op) => {
      const date = op.date;
      if (!groups[date]) {
        groups[date] = [];
      }
      groups[date].push(op);
    });
    return groups;
  }, [filteredOperations]);

  const sortedDates = useMemo(() => {
    return Object.keys(groupedByDate).sort().reverse();
  }, [groupedByDate]);

  // Форматирование даты для заголовка
  const formatDateHeader = (dateStr) => {
    const date = new Date(dateStr + 'T00:00:00');
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    
    const isToday = date.toDateString() === today.toDateString();
    const isYesterday = date.toDateString() === yesterday.toDateString();
    
    if (isToday) return '📅 Сегодня';
    if (isYesterday) return '📅 Вчера';
    
    const months = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
                    'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
    const day = date.getDate();
    const month = months[date.getMonth()];
    const year = date.getFullYear();
    
    return `📅 ${day} ${month} ${year}`;
  };

  const handleEdit = (item) => {
    setEditItem(item);
  };

  const handleSave = async (formData) => {
    if (!editItem) {
      return;
    }

    try {
      if (formData === null) {
        await api.deleteTimelineItem(editItem.id);
      } else {
        await api.updateTimelineItem(editItem.id, {
          ...formData,
          amount: Number(formData.amount),
        });
      }
      await loadOperations();
      showAlert?.('✅ Изменения сохранены');
    } catch (error) {
      console.error('Ошибка сохранения операции:', error);
      showAlert?.('❌ Ошибка при сохранении операции');
    } finally {
      setEditItem(null);
    }
  };

  if (loading) {
    return (
      <div className="p-6 pb-24">
        <div className="text-center py-12 text-gray-400">
          <div className="text-4xl mb-2">⏳</div>
          <div>Загрузка...</div>
        </div>
      </div>
    );
  }

  return (
   <div className="p-6 pb-24 space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-3xl font-bold">📋 Timeline</h2>
      </div>

      {/* Фильтр по периодам */}
      <div className="bg-white p-4 rounded-2xl shadow-sm space-y-3">
        <label className="font-medium text-gray-700">Период:</label>
        <select 
          value={period} 
          onChange={(e) => setPeriod(e.target.value)} 
          className="w-full p-3 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="month">📅 По месяцам</option>
          <option value="7">Последние 7 дней</option>
          <option value="30">Последние 30 дней</option>
          <option value="custom">Произвольный</option>
        </select>
        
        {period === 'month' && (
          <select
            value={selectedMonth}
            onChange={(e) => setSelectedMonth(e.target.value)}
            className="w-full p-3 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {monthOptions.map(option => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        )}
        
        {period === 'custom' && (
          <div className="flex gap-2">
            <DatePicker 
              selected={customStart} 
              onChange={date => setCustomStart(date)} 
              placeholderText="Дата начала"
              className="w-full p-3 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500"
              dateFormat="yyyy-MM-dd"
            />
            <DatePicker 
              selected={customEnd} 
              onChange={date => setCustomEnd(date)} 
              placeholderText="Дата конца"
              className="w-full p-3 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500"
              dateFormat="yyyy-MM-dd"
            />
          </div>
        )}
      </div>

      {/* Фильтры по типу операций */}
      <div className="flex gap-2 overflow-x-auto pb-2">
        {FILTERS.map(({ key, label, activeClass, idleClass }) => (
          <button
            key={key}
            onClick={() => setFilter(key)}
            className={`px-4 py-2 rounded-xl font-medium whitespace-nowrap transition-colors ${
              filter === key ? activeClass : idleClass
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Список операций, сгруппированный по дням */}
      {sortedDates.length === 0 ? (
        <div className="bg-white rounded-2xl p-6 text-center text-gray-500 shadow-sm">
          Нет операций по выбранному фильтру
        </div>
      ) : (
        <div className="space-y-6">
          {sortedDates.map((date) => (
            <div key={date} className="space-y-3">
              {/* Заголовок даты */}
              <div className="sticky top-0 z-10 bg-gradient-to-r from-gray-100 to-gray-50 px-4 py-2 rounded-xl">
                <div className="font-semibold text-gray-700">
                  {formatDateHeader(date)}
                </div>
                <div className="text-xs text-gray-500 mt-0.5">
                  {groupedByDate[date].length} {groupedByDate[date].length === 1 ? 'операция' : 
                   groupedByDate[date].length < 5 ? 'операции' : 'операций'}
                </div>
              </div>

              {/* Операции за этот день */}
              <div className="space-y-2">
                {groupedByDate[date].map((op) => (
                  <div
                    key={op.id}
                    className="bg-white rounded-2xl p-4 shadow-sm cursor-pointer hover:shadow-md transition"
                    onClick={() => handleEdit(op)}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3 flex-1">
                        <div
                          className={`
                            w-12 h-12 rounded-full flex items-center justify-center text-xl shrink-0
                            ${op.type === 'expense' ? 'bg-red-100 text-red-500' : ''}
                            ${op.type === 'income' ? 'bg-green-100 text-green-500' : ''}
                            ${op.type === 'transfer' ? 'bg-yellow-100 text-yellow-500' : ''}
                            ${op.type === 'incasation' ? 'bg-purple-100 text-purple-500' : ''}
                          `}
                        >
                          {op.type === 'expense'
                            ? '📉'
                            : op.type === 'income'
                            ? '📈'
                            : op.type === 'transfer'
                            ? '🔄'
                            : '🏦'}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="font-semibold text-gray-900">
                            {op.description || 'Операция'}
                          </div>
                          <div className="text-sm text-gray-500 flex items-center gap-2 flex-wrap">
                            {op.category_name && <span>{op.category_name}</span>}
                            {op.account_name && (
                              <>
                                {op.category_name && <span>•</span>}
                                <span>{op.account_name}</span>
                              </>
                            )}
                          </div>
                          {/* Информация об авторе */}
                          <div className="flex items-center justify-between mt-2 pt-2 border-t border-gray-100">
                            <div className="flex items-center gap-2">
                              <span className="text-xs text-gray-500">
                                👤 {op.created_by_name || op.created_by_username || 'Неизвестно'}
                              </span>
                              {op.created_by_username && (
                                <span className="text-xs text-gray-400">
                                  @{op.created_by_username}
                                </span>
                              )}
                            </div>
                            
                            {/* Индикатор: можно редактировать или нет */}
                            {op.user_id === parseInt(localStorage.getItem('current_user_id')) ? (
                              <span className="text-xs px-2 py-0.5 bg-green-50 text-green-600 rounded-full">
                                ✏️ Можно редактировать
                              </span>
                            ) : (
                              <span className="text-xs px-2 py-0.5 bg-gray-100 text-gray-500 rounded-full">
                                🔒 Только просмотр
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                      <div
                        className={`text-lg font-semibold shrink-0 ${
                          op.type === 'expense'
                            ? 'text-red-500'
                            : op.type === 'income'
                            ? 'text-green-500'
                            : op.type === 'transfer'
                            ? 'text-yellow-500'
                            : 'text-purple-500'
                        }`}
                      >
                        {op.type === 'expense' ? '-' : '+'}
                        {Number(op.amount || 0).toLocaleString()}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {editItem && (
        <EditModal
          item={editItem}
          onClose={() => setEditItem(null)}
          onSave={handleSave}
        />
      )}
    </div>
  );
}

